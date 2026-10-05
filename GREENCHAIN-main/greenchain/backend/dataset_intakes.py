from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from .db import create_dataset_intake


SCHEMA_VERSION = "scenario_csv_v1"
VALID_TRANSPORT_MODES = {"sea", "air", "rail", "road"}
REQUIRED_HEADERS = {
    "product",
    "quantity",
    "destination",
    "countries",
    "transport_mode",
}
OPTIONAL_HEADERS = {"require_certifications", "target_count"}
CANONICAL_HEADERS = REQUIRED_HEADERS | OPTIONAL_HEADERS
UPLOADS_DIR = Path(__file__).parent / "uploads"


class DatasetIntakeValidationError(ValueError):
    """Raised when an uploaded CSV fails the v1 intake contract."""


@dataclass(frozen=True)
class ParsedScenarioCsv:
    headers: list[str]
    normalized: dict[str, Any]
    row_count: int


def _normalize_header(header: str) -> str:
    return header.strip().lower()


def _split_pipe_list(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _parse_csv_text(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader]


def _build_row_map(headers: list[str], row: list[str]) -> dict[str, str]:
    if len(row) > len(headers):
        raise DatasetIntakeValidationError("Row has more columns than the header.")

    padded = row + [""] * (len(headers) - len(row))
    return {
        header: value.strip()
        for header, value in zip(headers, padded)
    }


def parse_and_validate_scenario_csv_text(text: str) -> ParsedScenarioCsv:
    rows = _parse_csv_text(text)
    if not rows:
        raise DatasetIntakeValidationError(
            "CSV must include a header row and one data row."
        )

    raw_headers = rows[0]
    if not any(header.strip() for header in raw_headers):
        raise DatasetIntakeValidationError(
            "CSV must include a header row and one data row."
        )

    headers: list[str] = []
    seen_headers: set[str] = set()
    for raw_header in raw_headers:
        normalized_header = _normalize_header(raw_header)
        if not normalized_header:
            raise DatasetIntakeValidationError("Header names cannot be empty.")
        if normalized_header in seen_headers:
            raise DatasetIntakeValidationError(
                f"Duplicate header: {normalized_header}"
            )
        seen_headers.add(normalized_header)
        headers.append(normalized_header)

    missing_headers = sorted(REQUIRED_HEADERS - set(headers))
    if missing_headers:
        missing_headers_text = ", ".join(missing_headers)
        raise DatasetIntakeValidationError(
            f"Missing required header(s): {missing_headers_text}"
        )

    data_rows = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    if not data_rows:
        raise DatasetIntakeValidationError("CSV must include one scenario row.")
    if len(data_rows) > 1:
        raise DatasetIntakeValidationError(
            "This version accepts one scenario per upload."
        )

    row_map = _build_row_map(headers, data_rows[0])

    product = row_map.get("product", "").strip()
    if not product:
        raise DatasetIntakeValidationError("Product is required.")

    quantity_text = row_map.get("quantity", "").strip()
    try:
        quantity = float(quantity_text)
    except ValueError as exc:
        raise DatasetIntakeValidationError(
            "Quantity must be a positive number."
        ) from exc
    if quantity <= 0:
        raise DatasetIntakeValidationError("Quantity must be a positive number.")

    destination = row_map.get("destination", "").strip()
    if not destination:
        raise DatasetIntakeValidationError("Destination is required.")

    transport_mode = row_map.get("transport_mode", "").strip().lower()
    if transport_mode not in VALID_TRANSPORT_MODES:
        valid_modes = ", ".join(sorted(VALID_TRANSPORT_MODES))
        raise DatasetIntakeValidationError(
            f"transport_mode must be one of: {valid_modes}."
        )

    target_count_text = row_map.get("target_count", "").strip()
    target_count: int | None = None
    if target_count_text:
        try:
            target_count = int(target_count_text)
        except ValueError as exc:
            raise DatasetIntakeValidationError(
                "target_count must be a positive whole number."
            ) from exc
        if target_count <= 0:
            raise DatasetIntakeValidationError(
                "target_count must be a positive whole number."
            )

    normalized = {
        "product": product,
        "quantity": quantity,
        "destination": destination,
        "countries": _split_pipe_list(row_map.get("countries", "")),
        "transport_mode": transport_mode,
        "require_certifications": _split_pipe_list(
            row_map.get("require_certifications", "")
        ),
        "target_count": target_count,
    }

    return ParsedScenarioCsv(
        headers=headers,
        normalized=normalized,
        row_count=len(data_rows),
    )


def _sanitize_filename(filename: str) -> str:
    basename = Path(filename).name or "scenario.csv"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", basename).strip("-")
    return safe_name or "scenario.csv"


async def store_dataset_intake_upload(file: UploadFile) -> dict[str, Any]:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise DatasetIntakeValidationError("Only .csv files are supported.")

    file_bytes = await file.read()
    if not file_bytes:
        raise DatasetIntakeValidationError(
            "CSV must include a header row and one data row."
        )

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetIntakeValidationError("CSV must be UTF-8 encoded.") from exc

    parsed = parse_and_validate_scenario_csv_text(text)

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    intake_id = f"intake_{uuid.uuid4().hex[:12]}"
    safe_filename = _sanitize_filename(filename)
    stored_path = UPLOADS_DIR / f"{intake_id}_{safe_filename}"
    stored_path.write_bytes(file_bytes)

    create_dataset_intake(
        intake_id=intake_id,
        filename=safe_filename,
        stored_path=str(stored_path),
        row_count=parsed.row_count,
        status="uploaded",
        schema_version=SCHEMA_VERSION,
    )

    return {
        "filename": safe_filename,
        "id": intake_id,
        "row_count": parsed.row_count,
        "schema_version": SCHEMA_VERSION,
        "status": "uploaded",
    }
