"""Carry an approved procurement's preserved context into a PROXY draft.

The reference adapter is a simulator. The native adapter calls the inspected
CONSUMER-main API over HTTP; it never imports or copies that project's source.
Neither adapter sends a complaint, changes an appeal to ``sent``, or declares a
legal entitlement. Authentication/session mapping belongs to the coordinator.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

MAX_BUNDLE_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
SCHEMA_VERSION = "peoplepay.dispute-evidence.v1"


def _text(value: Any, name: str, maximum: int = 200) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        raise ValueError(f"{name} must be nonempty text of at most {maximum} characters")
    return value.strip()


def _canonical(value: Any) -> bytes:
    # Bound nesting independently of Python's recursion limit. This also
    # protects native responses parsed under a test runner's larger limit.
    pending = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > 12:
            raise ValueError("PROXY evidence/response JSON nesting exceeds 12 levels")
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    try:
        raw = json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeEncodeError) as exc:
        raise ValueError("Dispute context must contain finite JSON values") from exc
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("Dispute evidence exceeds the 512 KiB limit")
    return raw


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name} must be a nonempty object")
    return json.loads(_canonical(value))


def _quantity(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 1_000_000:
        raise ValueError(f"{name} must be an integer between {minimum} and 1000000")
    return value


def build_bundle(
    *,
    requirement: dict[str, Any] | str,
    decision: dict[str, Any],
    selected_supplier: dict[str, Any],
    approved_terms: dict[str, Any],
    transaction_reference: str,
    merchant_order_reference: str,
    delivery_event: dict[str, Any],
    actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Snapshot and hash all context needed to explain a delivery discrepancy.

    The caller must supply the persisted approved decision and terms, never a
    freshly refreshed decision. The hash detects subsequent modification; the
    owner-scoped journey store remains the authority for the snapshot's origin.
    This adapter handles partial-delivery issues only.
    """
    if isinstance(requirement, str):
        if not requirement.strip() or len(requirement) > 20_000:
            raise ValueError("requirement must be nonempty and at most 20000 characters")
        original_requirement: dict[str, Any] | str = requirement
    else:
        original_requirement = _object(requirement, "requirement")
    terms = _object(approved_terms, "approved_terms")
    event = _object(delivery_event, "delivery_event")
    supplier = _object(selected_supplier, "selected_supplier")
    approved_decision = _object(decision, "decision")
    owner = _text(actor_id, "actor_id")
    transaction = _text(transaction_reference, "transaction_reference")
    approved_quantity = _quantity(terms.get("quantity"), "approved_terms.quantity", 1)
    payload = event.get("data", event)
    if not isinstance(payload, dict):
        raise ValueError("delivery_event.data must be an object")
    delivered_quantity = _quantity(payload.get("delivered_quantity"), "delivered_quantity")
    if delivered_quantity >= approved_quantity:
        raise ValueError("This draft requires a partial delivery below the approved quantity")
    order_reference = _text(merchant_order_reference, "merchant_order_reference")
    event_order = payload.get("merchant_order_reference")
    if event_order != order_reference:
        raise ValueError("Delivery event belongs to another merchant order")
    if "ordered_quantity" in payload and _quantity(payload["ordered_quantity"], "ordered_quantity", 1) != approved_quantity:
        raise ValueError("Delivery event ordered quantity differs from approved terms")
    if "missing_quantity" in payload and _quantity(payload["missing_quantity"], "missing_quantity") != approved_quantity - delivered_quantity:
        raise ValueError("Delivery event missing quantity differs from approved terms")
    if "delivery_final" in payload and payload["delivery_final"] is not True:
        raise ValueError("A delivery dispute requires a final delivery receipt")
    for key, expected in (("merchant_order_ref", order_reference), ("transaction_id", transaction), ("actor_id", owner)):
        if key in event and event[key] != expected:
            raise ValueError(f"Delivery event {key} differs from the approved transaction")
    for key, expected in (("actor_id", owner), ("transaction_id", transaction)):
        if key in approved_decision and approved_decision[key] != expected:
            raise ValueError(f"Decision {key} differs from the approved transaction")
    if isinstance(original_requirement, dict) and "quantity" in original_requirement:
        if _quantity(original_requirement["quantity"], "requirement.quantity", 1) != approved_quantity:
            raise ValueError("Original requirement quantity differs from approved terms")
    if "supplier_id" in terms and terms["supplier_id"] != supplier.get("supplier_id", supplier.get("id")):
        raise ValueError("Selected supplier differs from approved terms")
    for key in ("decision_id", "decision_version"):
        if key in event and key in approved_decision and event[key] != approved_decision[key]:
            raise ValueError(f"Delivery event {key} differs from the approved decision")
    if "decision_version" in event and (type(event["decision_version"]) is not int or event["decision_version"] < 1):
        raise ValueError("Delivery event decision_version must be a positive integer")
    if "requirement" in approved_decision and _canonical(approved_decision["requirement"]) != _canonical(original_requirement):
        raise ValueError("Original requirement differs from the preserved decision")
    decision_hash = approved_decision.get("decision_hash")
    if decision_hash is not None:
        snapshot = {key: value for key, value in approved_decision.items() if key != "decision_hash"}
        actual_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=True, allow_nan=False).encode()).hexdigest()
        if not isinstance(decision_hash, str) or not hmac.compare_digest(decision_hash, actual_hash):
            raise ValueError("Preserved decision hash does not match its snapshot")
    candidates = approved_decision.get("candidates")
    if candidates is not None:
        if not isinstance(candidates, list):
            raise ValueError("Decision candidates must be a list")
        selected = next((candidate for candidate in candidates if isinstance(candidate, dict)
                         and candidate.get("supplier_id") == terms.get("supplier_id")), None)
        if selected is None or _canonical(selected.get("terms")) != _canonical(terms) or selected.get("eligible") is not True:
            raise ValueError("Approved terms do not match an eligible candidate in the preserved decision")
    context = {
        "schema_version": SCHEMA_VERSION,
        "actor_id": owner,
        "correlation_id": _text(correlation_id, "correlation_id"),
        "requirement": original_requirement,
        "decision": approved_decision,
        "selected_supplier": supplier,
        "approved_terms": terms,
        "transaction_reference": transaction,
        "merchant_order_reference": order_reference,
        "delivery_event": event,
        "discrepancy": {
            "kind": "partial_delivery",
            "ordered_quantity": approved_quantity,
            "delivered_quantity": delivered_quantity,
            "missing_quantity": approved_quantity - delivered_quantity,
        },
    }
    # This serialization also detaches nested evidence/raw-provider state from
    # mutable inputs and bounds the complete bundle rather than each fragment.
    raw = _canonical(context)
    snapshot = json.loads(raw)
    bundle = {**snapshot, "bundle_hash": hashlib.sha256(raw).hexdigest()}
    _canonical(bundle)
    return bundle


def verify_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return a detached copy only when the complete evidence hash still agrees."""
    if not isinstance(bundle, dict) or bundle.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported dispute evidence schema")
    expected = bundle.get("bundle_hash")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Missing dispute evidence hash")
    context = {key: value for key, value in bundle.items() if key != "bundle_hash"}
    expected_fields = {
        "schema_version", "actor_id", "correlation_id", "requirement", "decision",
        "selected_supplier", "approved_terms", "transaction_reference",
        "merchant_order_reference", "delivery_event", "discrepancy",
    }
    if set(context) != expected_fields:
        raise ValueError("Dispute evidence has missing or unsupported fields")
    actual = hashlib.sha256(_canonical(context)).hexdigest()
    if not hmac.compare_digest(expected, actual):
        raise ValueError("Dispute evidence changed after snapshot")
    # Revalidate relationships too: a hash is integrity evidence, not authority.
    rebuilt = build_bundle(**{
        key: context[key] for key in (
            "requirement", "decision", "selected_supplier", "approved_terms",
            "transaction_reference", "merchant_order_reference", "delivery_event",
            "actor_id", "correlation_id",
        )
    })
    if not hmac.compare_digest(rebuilt["bundle_hash"], expected):
        raise ValueError("Dispute evidence contains inconsistent or unsupported fields")
    return json.loads(_canonical(bundle))


def _supplier_name(bundle: dict[str, Any]) -> str:
    supplier = bundle["selected_supplier"]
    return _text(supplier.get("name") or supplier.get("display_name"), "supplier name", 160)


def _draft_text(bundle: dict[str, Any]) -> str:
    issue = bundle["discrepancy"]
    return (
        "DRAFT — HUMAN REVIEW REQUIRED\n\n"
        f"To {_supplier_name(bundle)},\n\n"
        f"Regarding merchant order {bundle['merchant_order_reference']} and PeoplePay "
        f"transaction {bundle['transaction_reference']}: the preserved approved terms "
        f"request {issue['ordered_quantity']} units. The linked delivery event records "
        f"{issue['delivered_quantity']} units delivered, leaving {issue['missing_quantity']} "
        "units unaccounted for. Please investigate this discrepancy and propose a "
        "delivery completion or other remedy for the buyer to review.\n\n"
        f"Evidence bundle: SHA-256 {bundle['bundle_hash']}. The attached bundle contains "
        "the original requirement, approved decision and source evidence, selected "
        "supplier, approved terms, transaction and order references, and delivery event.\n\n"
        "This draft has not been submitted. Confirm the delivery record and approved "
        "terms before choosing a remedy or sending this document."
    )


class ReferenceProxyAdapter:
    """Deterministic local PROXY contract simulator, with no submission behavior."""

    def create_draft(self, bundle: dict[str, Any]) -> dict[str, Any]:
        preserved = verify_bundle(bundle)
        return {
            "draft_id": f"proxy-reference-{preserved['bundle_hash'][:24]}",
            "provider": "PROXY reference simulator",
            "mode": "REFERENCE_SIMULATOR",
            "status": "draft",
            "submitted": False,
            "requires_human_review": True,
            "evidence_class": "UNVERIFIED_DRAFT",
            "bundle_hash": preserved["bundle_hash"],
            "bundle": preserved,
            "draft_text": _draft_text(preserved),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "warnings": [
                "Reference draft simulator; the native PROXY agent workflow did not run.",
                "Partial delivery is recorded evidence, not a legal finding or agreed remedy.",
            ],
        }


def create_draft(bundle: dict[str, Any]) -> dict[str, Any]:
    """Default local reference draft. Use NativeProxyAdapter for a real service."""
    return ReferenceProxyAdapter().create_draft(bundle)


class NativeProxyError(RuntimeError):
    """A bounded native handoff failed; progress is available for safe recovery.

    Native PROXY has no idempotency key on case creation. Do not retry creation
    automatically after an ambiguous response; reconcile the user's case list.
    """

    def __init__(self, message: str, *, case_id: str | None = None) -> None:
        super().__init__(message)
        self.case_id = case_id


class NativeProxyAdapter:
    """Exact inspected PROXY case/upload/appeal API with an explicit user session.

    base_url is operator configuration, not a browser-supplied destination.
    bearer_token must be the mapped user's native PROXY token; it is never
    written into evidence or returned to the coordinator. No automatic retries.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_prefix: str = "/api/v1",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("PROXY base_url must be an HTTP(S) origin without credentials")
        if parsed.scheme == "http" and parsed.hostname != "localhost":
            try:
                loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise ValueError("Native PROXY user tokens require HTTPS outside loopback")
        if not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", api_prefix) or len(api_prefix) > 100:
            raise ValueError("Invalid PROXY API prefix")
        if not 1 <= timeout <= 120:
            raise ValueError("Native PROXY timeout must be between 1 and 120 seconds")
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix
        self.timeout = timeout
        self.transport = transport

    def create_draft(
        self,
        bundle: dict[str, Any],
        *,
        bearer_token: str,
        proxy_user_id: str,
        native_case_id: str | None = None,
    ) -> dict[str, Any]:
        preserved = verify_bundle(bundle)
        token = _text(bearer_token, "bearer_token", 16_384)
        if not token.isascii() or any(char.isspace() for char in token):
            raise ValueError("Native PROXY bearer_token must be an ASCII token without whitespace")
        expected_user = _text(proxy_user_id, "proxy_user_id")
        case_id = _text(native_case_id, "native_case_id") if native_case_id is not None else None
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-Request-ID": str(uuid.uuid4()),
        }
        issue = preserved["discrepancy"]
        summary = (
            f"Delivery discrepancy for {preserved['merchant_order_reference']}: "
            f"approved {issue['ordered_quantity']} units, delivery event records "
            f"{issue['delivered_quantity']}, missing {issue['missing_quantity']}. "
            f"PeoplePay transaction {preserved['transaction_reference']}; evidence "
            f"SHA-256 {preserved['bundle_hash']}. Complete original context is attached "
            "as peoplepay-evidence.json. Draft only; human review required."
        )
        # Verify before creation that this request cannot exceed native fields.
        if len(summary) > 4000:
            raise ValueError("Native PROXY summary exceeds 4000 characters")
        with httpx.Client(
            timeout=self.timeout, follow_redirects=False, transport=self.transport,
            headers=headers, trust_env=False,
        ) as client:
            if case_id:
                case = self._request(client, "GET", f"/cases/{quote(case_id, safe='')}", case_id=case_id)
            else:
                case = self._request(client, "POST", "/cases", json={
                    "domain": "ecommerce",
                    "title": "PeoplePay partial delivery dispute",
                    "institution_name": _supplier_name(preserved),
                    "summary": summary,
                    "jurisdiction": "IN",
                })
            try:
                returned_case_id = _text(case.get("id"), "native case id")
            except ValueError as exc:
                raise NativeProxyError("Native PROXY returned no valid case identifier", case_id=case_id) from exc
            if case_id is not None and returned_case_id != case_id:
                raise NativeProxyError("Native PROXY returned a different resume case", case_id=case_id)
            case_id = returned_case_id
            if case.get("user_id") != expected_user:
                raise NativeProxyError("Native PROXY returned a case for another mapped user", case_id=case_id)
            if case.get("domain") != "ecommerce" or case.get("status") not in {
                "draft", "intake", "review_required", "ready_for_approval",
            }:
                raise NativeProxyError("Native PROXY case is not an open ecommerce draft workflow", case_id=case_id)
            if native_case_id and (
                not isinstance(case.get("summary"), str)
                or preserved["bundle_hash"] not in case["summary"]
                or case.get("institution_name") != _supplier_name(preserved)
            ):
                raise NativeProxyError("Native PROXY resume case does not match this evidence bundle", case_id=case_id)
            document = self._request(
                client, "POST", "/case/upload", case_id=case_id,
                data={"case_id": case_id, "document_type": "peoplepay_transaction_evidence"},
                files={"file": ("peoplepay-evidence.json", _canonical(preserved), "application/json")},
            )
            if document.get("case_id") != case_id or document.get("user_id") != expected_user:
                raise NativeProxyError("Native PROXY returned evidence for another case or user", case_id=case_id)
            try:
                document_id = _text(document.get("id") or document.get("document_id"), "native document id")
            except ValueError as exc:
                raise NativeProxyError("Native PROXY returned no valid evidence document identifier", case_id=case_id) from exc
            analysis = self._request(
                client, "POST", "/case/appeal", case_id=case_id, json={"case_id": case_id}
            )
            if analysis.get("case_id") != case_id:
                raise NativeProxyError("Native PROXY returned analysis for another case", case_id=case_id)
            if ("user_id" in analysis and analysis["user_id"] != expected_user) or analysis.get("submitted") is True:
                raise NativeProxyError("Native PROXY returned analysis outside this user's draft workflow", case_id=case_id)
            if "status" in analysis and analysis["status"] not in {"draft", "review_required", "ready_for_approval"}:
                raise NativeProxyError("Native PROXY analysis is not a draft awaiting human review", case_id=case_id)
            draft_text = analysis.get("appeal_draft")
            if not isinstance(draft_text, str) or not draft_text.strip():
                raise NativeProxyError("Native PROXY produced no appeal draft; review its provider configuration", case_id=case_id)
        return {
            "draft_id": f"proxy-native-{case_id}-{preserved['bundle_hash'][:16]}",
            "native_case_id": case_id,
            "native_document_id": document_id,
            "provider": "PROXY native service",
            "mode": "NATIVE_SERVICE",
            "status": "draft",
            "submitted": False,
            "requires_human_review": True,
            "evidence_class": "UNVERIFIED_DRAFT",
            "bundle_hash": preserved["bundle_hash"],
            "bundle": preserved,
            "draft_text": draft_text,
            "native_response": analysis,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "warnings": [
                "Native PROXY drafted an argument; it has not submitted a complaint.",
                "Native case creation has no idempotency contract; reconcile ambiguous failures before retrying.",
            ],
        }

    def _request(
        self, client: httpx.Client, method: str, path: str,
        *, case_id: str | None = None, **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            with client.stream(method, f"{self.base_url}{self.api_prefix}{path}", **kwargs) as response:
                if not 200 <= response.status_code < 300:
                    raise NativeProxyError(f"Native PROXY {path} returned HTTP {response.status_code}", case_id=case_id)
                raw = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise NativeProxyError("Native PROXY response exceeded 512 KiB", case_id=case_id)
            def reject_constant(value: str) -> None:
                raise ValueError(f"Nonfinite JSON constant {value}")

            def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate JSON object key")
                    result[key] = value
                return result

            decoded = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=reject_duplicate_keys)
            _canonical(decoded)
        except (httpx.HTTPError, ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise NativeProxyError(f"Native PROXY {path} failed or returned invalid JSON", case_id=case_id) from exc
        if not isinstance(decoded, dict):
            raise NativeProxyError("Native PROXY returned a nonobject response", case_id=case_id)
        return decoded
