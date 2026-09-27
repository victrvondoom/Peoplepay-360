from __future__ import annotations

from enum import Enum

from app.models.domain import Domain
from app.services.document_relevance import check_document_relevance


class DocumentType(str, Enum):
    POLICY = "policy"
    MEDICAL_REPORT = "medical_report"
    REJECTION_LETTER = "rejection_letter"
    BILL = "bill"
    OTHER = "other"


POLICY_KEYWORDS = ("policy", "wording", "prospectus", "terms", "coverage", "brochure")
MEDICAL_KEYWORDS = ("medical", "discharge", "diagnosis", "prescription", "doctor", "hospital record", "lab", "mri", "ct")
REJECTION_KEYWORDS = ("rejection", "denial", "denied", "repudiation", "claim rejection", "declined")
BILL_KEYWORDS = ("bill", "invoice", "receipt", "hospital bill", "pharmacy", "payment", "charges")


def classify_document(filename: str, mime_type: str | None = None) -> DocumentType:
    lower = filename.lower()
    if any(k in lower for k in REJECTION_KEYWORDS):
        return DocumentType.REJECTION_LETTER
    if any(k in lower for k in MEDICAL_KEYWORDS):
        return DocumentType.MEDICAL_REPORT
    if any(k in lower for k in BILL_KEYWORDS):
        return DocumentType.BILL
    if any(k in lower for k in POLICY_KEYWORDS):
        return DocumentType.POLICY
    if lower.endswith(".pdf"):
        return DocumentType.OTHER
    return DocumentType.OTHER


def _relevant_documents(documents: list[dict], domain: str | Domain | None) -> list[dict]:
    """Return only documents that pass the domain relevance check."""
    if not domain:
        return documents
    # Resolve string → Domain enum if needed
    if isinstance(domain, str):
        try:
            domain = Domain(domain)
        except ValueError:
            return documents
    relevant = []
    for doc in documents:
        text = (doc.get("text_extract") or "").strip()
        filename = doc.get("filename", "")
        if not text:
            # No text (e.g. image) — keep it, can't check
            relevant.append(doc)
            continue
        is_ok, _ = check_document_relevance(text, domain, filename=filename)
        if is_ok:
            relevant.append(doc)
    return relevant


def build_case_summary(case: dict, documents: list[dict]) -> str:
    domain = case.get("domain")
    filtered = _relevant_documents(documents, domain)
    sections = [
        f"Case: {case.get('title', '')}",
        f"Insurer: {case.get('institution_name', '')}",
        f"Summary: {case.get('summary', '')}",
        f"Jurisdiction: {case.get('jurisdiction', 'IN')}",
    ]
    by_type: dict[str, list[str]] = {}
    for doc in filtered:
        doc_type = doc.get("document_type") or DocumentType.OTHER.value
        by_type.setdefault(doc_type, []).append(doc.get("filename", "document"))
    if by_type:
        sections.append("Uploaded documents:")
        for doc_type, names in by_type.items():
            sections.append(f"  - {doc_type}: {', '.join(names)}")
    skipped = len(documents) - len(filtered)
    if skipped:
        sections.append(f"  ({skipped} unrelated document(s) excluded from analysis)")
    return "\n".join(sections)


def build_evidence_bundle(documents: list[dict], domain: str | Domain | None = None) -> str:
    # Deliberately returns "" (not a "No documents uploaded" placeholder
    # sentence) when there's genuinely nothing to show -- every caller
    # (evidence_prompt, build_agent_prompt, and all 6 domain specialists'
    # `if evidence_bundle else "..."` checks) already renders its own
    # correct fallback message on falsy input. A truthy placeholder string
    # here made every one of those checks treat "no evidence" as "evidence
    # exists", which fed the model a literal "Uploaded Case Evidence:
    # No uploaded evidence documents." block and had it judge that
    # placeholder's "relevance" -- producing evidence_facts hallucinated
    # from the query text and headers like "Facts confirmed from your
    # uploaded document" when the user uploaded nothing at all.
    if not documents:
        return ""
    # Filter out unrelated documents so they never reach the LLM
    filtered = _relevant_documents(documents, domain) if domain else documents
    parts: list[str] = []
    for doc in filtered:
        doc_type = doc.get("document_type", DocumentType.OTHER.value)
        text = (doc.get("text_extract") or "").strip()
        if not text:
            continue
        parts.append(f"=== {doc_type.upper()}: {doc.get('filename', 'document')} ===\n{text[:8000]}")
    return "\n\n".join(parts)
