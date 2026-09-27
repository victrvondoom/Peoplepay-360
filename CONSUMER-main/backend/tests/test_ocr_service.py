from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import get_settings
from app.services.ocr_service import OCRService, ocr_service


def _enable_ocr(monkeypatch) -> None:
    monkeypatch.setenv("DISABLE_EXTERNAL_LLM", "false")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_extract_image_uses_vision_ocr(monkeypatch):
    service = OCRService()
    _enable_ocr(monkeypatch)

    with patch.object(service, "_vision_ocr", AsyncMock(return_value="Policy Number: ABC123")) as vision:
        result = await service.extract_image(b"fake-image", "image/jpeg")

    vision.assert_awaited_once()
    assert result.text == "Policy Number: ABC123"
    assert result.method == "ocr"
    assert result.pages_ocrd == 1


@pytest.mark.asyncio
async def test_extract_pdf_uses_native_text_when_sufficient(monkeypatch):
    service = OCRService()
    _enable_ocr(monkeypatch)

    native_pages = ["A" * 120, "B" * 120]
    with patch.object(service, "_native_pdf_pages", return_value=native_pages):
        with patch.object(service, "_render_pdf_pages", return_value=[]) as render:
            result = await service.extract_pdf(b"%PDF")

    render.assert_not_called()
    assert result.method == "native"
    assert len(result.text) >= 240


@pytest.mark.asyncio
async def test_extract_pdf_ocrs_sparse_pages_only(monkeypatch):
    service = OCRService()
    _enable_ocr(monkeypatch)

    native_pages = ["Short", ""]
    rendered = [(1, b"img", "image/jpeg")]

    with patch.object(service, "_native_pdf_pages", return_value=native_pages):
        with patch.object(service, "_render_pdf_pages", return_value=rendered):
            with patch.object(service, "_ocr_pages_parallel", AsyncMock(return_value=["Scanned page text"])) as ocr_pages:
                result = await service.extract_pdf(b"%PDF")

    ocr_pages.assert_awaited_once()
    assert "Scanned page text" in result.text
    assert result.method in {"ocr", "mixed"}
    assert result.pages_ocrd == 1


def test_prepare_image_bytes_downscales_large_images(monkeypatch):
    from PIL import Image

    service = OCRService()
    monkeypatch.setenv("OCR_MAX_IMAGE_SIDE", "800")
    get_settings.cache_clear()

    image = Image.new("RGB", (2400, 1200), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    prepared = service._prepare_image_bytes(buffer.getvalue(), "image/png")

    out = Image.open(io.BytesIO(prepared))
    assert max(out.size) <= 800


def test_singleton_exists():
    assert isinstance(ocr_service, OCRService)
