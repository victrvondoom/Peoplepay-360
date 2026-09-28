"""Dispute and refund resolution, fronting PROXY (spec Sec. 32, Sec. 45).

The lifecycle in ``beacon.assurance.states`` declares a whole failure path --
``DELIVERY_FAILED`` -> ``REFUND_REQUIRED`` -> ``DISPUTE_REQUIRED`` ->
``RESOLUTION_PENDING`` -> ``RESOLVED`` -- and nothing implemented it.  PROXY
does exactly that work: it researches the applicable regulation from an indexed
corpus, extracts evidence from uploaded documents, drafts an appeal or regulator
complaint, and runs a Review agent that gates its own output and forces a retry
on a hallucinated citation.

The original brief expected this project to be a booking agent.  It is not; it is
a consumer-justice system, and that makes it a better fit for the part of a
transaction most systems abandon -- what happens after the money has gone and the
goods are wrong.

**Licensing boundary.**  ``CONSUMER-main`` carries no licence at any level (see
``docs/licensing-blockers.md``), so default copyright applies and none of its
source may be vendored.  This adapter therefore talks to PROXY strictly over
HTTP, as a service somebody else operates under their own terms.  Nothing here
is copied from it; the endpoint shapes below are interface facts.

**What PROXY produces is a draft, not a finding.**  An appeal letter is an
argument the user may choose to send.  A strategy is a plan.  Neither is a fact
about the world, and neither may become decision-grade evidence -- so every
drafted artifact is capped at ``UNVERIFIED`` and marked ``requires_human_review``.
What *can* carry more weight is narrower and handled separately: PROXY's own
deterministic citation verifier splits claims it could confirm against the
retrieved corpus from claims it could not, and that split is carried across
honestly instead of averaged away.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from beacon.assurance.evidence import EvidenceClass, Observation, content_hash

from adapters.base import Capability, CapabilityMode, CapabilityResult, HealthReport

__all__ = ["DISPUTE_DOMAINS", "ResolutionAdapter"]


#: The eight domains PROXY routes between.  Named here so a caller cannot pass a
#: domain PROXY will silently fall back on.
DISPUTE_DOMAINS: frozenset[str] = frozenset(
    {
        "airlines",
        "banking",
        "ecommerce",
        "government",
        "healthcare",
        "health_insurance",
        "housing",
        "telecom",
    }
)

_DRAFT_NOTE = (
    "DRAFTED BY AN AGENT: an argument the user may choose to send, not a "
    "finding. Requires human review before it leaves the system."
)


class ResolutionAdapter(Capability):
    """Dispute, refund and resolution workflows from PROXY."""

    name = "resolution"
    upstream = "PROXY / CONSUMER (UNLICENSED - service boundary only)"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        mode_override: CapabilityMode | None = None,
    ) -> None:
        # A dispute workflow runs several agents in sequence, so the default
        # timeout is generous; a short one would report a working system as down.
        self.base_url = (base_url or os.getenv("BEACON_RESOLUTION_URL") or "").rstrip(
            "/"
        )
        self.timeout = timeout
        self._mode_override = mode_override

    # ------------------------------------------------------------------

    def health(self) -> HealthReport:
        if self._mode_override is not None:
            return HealthReport(
                name=self.name,
                mode=self._mode_override,
                detail="mode pinned by caller",
                endpoint=self.base_url or None,
                upstream=self.upstream,
            )
        if not self.base_url:
            return HealthReport(
                name=self.name,
                mode=CapabilityMode.NOT_CONFIGURED,
                detail=(
                    "no PROXY endpoint configured; it runs as a separate service "
                    "with its own Qdrant, Neo4j, Redis and Gemini credentials, and "
                    "is unlicensed so it cannot be embedded here"
                ),
                missing_config=("BEACON_RESOLUTION_URL",),
                upstream=self.upstream,
            )
        try:
            body = self._request("GET", "/health")
        except Exception as exc:  # noqa: BLE001 - health must not raise
            return HealthReport(
                name=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                detail=f"{type(exc).__name__}: {exc}",
                endpoint=self.base_url,
                upstream=self.upstream,
            )
        status = ""
        if isinstance(body, dict):
            status = str(body.get("status") or body.get("state") or "")
        return HealthReport(
            name=self.name,
            mode=CapabilityMode.LIVE,
            detail=f"PROXY reachable{f' (status={status})' if status else ''}",
            endpoint=self.base_url,
            upstream=self.upstream,
        )

    # ------------------------------------------------------------------
    # running a dispute
    # ------------------------------------------------------------------

    def run_case(self, *, case_id: str, include_draft: bool = True) -> CapabilityResult:
        """Run PROXY's workflow for an already-created case.

        Returns the drafted artifacts as reviewable content and the citation
        split as evidence.  Never returns a "resolved" verdict: closing a
        transaction's exception is the lifecycle's decision, not PROXY's.
        """
        if not case_id.strip():
            raise ValueError("a case_id is required to run a dispute workflow")
        report = self.health()
        if report.mode in (CapabilityMode.NOT_CONFIGURED, CapabilityMode.UNAVAILABLE):
            return self.unconfigured_result(
                gaps=("dispute_strategy", "verified_citations")
            )

        try:
            body = self._request(
                "POST",
                "/run-case",
                payload={
                    "case_id": case_id,
                    "include_negotiation_draft": include_draft,
                },
            )
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            return CapabilityResult(
                capability=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                payload={"error": detail, "case_id": case_id},
                observations=(
                    self.missing(
                        "dispute_strategy", note=f"PROXY did not answer: {detail}"
                    ),
                ),
                gaps=("dispute_strategy", "verified_citations"),
            )

        if not isinstance(body, dict):
            return CapabilityResult(
                capability=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                payload={"error": "PROXY returned a non-object body"},
                observations=(self.missing("dispute_strategy"),),
                gaps=("dispute_strategy",),
            )

        observations: list[Observation] = []

        # --- the drafts: arguments, not facts ---------------------------
        for field in ("strategy", "appeal_draft"):
            text = str(body.get(field) or "").strip()
            if not text:
                observations.append(
                    self.missing(field, note=f"PROXY produced no {field}")
                )
                continue
            observations.append(
                self.observe(
                    field,
                    text,
                    # A drafted argument is never a verified fact about the world.
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note=_DRAFT_NOTE,
                    raw_reference=case_id,
                )
            )

        # --- the citation split: this part is real ----------------------
        citations = [str(c) for c in (body.get("citations") or []) if str(c).strip()]
        review_notes = [str(n) for n in (body.get("review_notes") or [])]
        if citations:
            observations.append(
                self.observe(
                    "citations",
                    citations,
                    # PROXY verifies these against its retrieved corpus rather
                    # than against the regulator, so UNVERIFIED is the ceiling.
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note=(
                        f"{len(citations)} citation(s) passed PROXY's deterministic "
                        "verification against its indexed corpus; corpus-confirmed "
                        "is not regulator-confirmed"
                    ),
                    raw_hash=content_hash(citations),
                )
            )
        else:
            observations.append(
                self.missing(
                    "verified_citations",
                    note="PROXY returned no citations it could verify",
                )
            )
        if review_notes:
            observations.append(
                self.observe(
                    "review_notes",
                    review_notes,
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note=(
                        "PROXY's own Review agent flagged these; an unresolved "
                        "flag is a reason for a human to look, not to proceed"
                    ),
                )
            )

        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload={
                "case_id": case_id,
                "proxy_status": str(body.get("status") or "unknown"),
                "route": body.get("route", ""),
                "citation_count": len(citations),
                "review_note_count": len(review_notes),
                "llm_call_count": body.get("llm_call_count", 0),
                "workflow_engine": body.get("workflow_engine", ""),
                "has_appeal_draft": bool(str(body.get("appeal_draft") or "").strip()),
                # The two flags a reviewer needs before acting on any of this.
                "requires_human_review": True,
                "artifacts_are_drafts": True,
                "resolution_note": (
                    "PROXY drafts and argues; it does not settle a transaction. "
                    "Moving a transaction to RESOLVED remains a lifecycle "
                    "decision taken on the evidence, not a status copied from here."
                ),
            },
            observations=tuple(observations),
            gaps=() if citations else ("verified_citations",),
            subsystem_ref=f"proxy:case:{case_id}",
            # Deliberately low: an unreviewed draft should not look confident.
            confidence=0.4,
        )

    # ------------------------------------------------------------------
    # asking a question
    # ------------------------------------------------------------------

    def ask(
        self,
        *,
        question: str,
        domain: str = "ecommerce",
        institution_name: str = "",
    ) -> CapabilityResult:
        """Ask PROXY a regulation question for one domain.

        Used when a transaction hits an exception and we need to know what the
        user's rights are before drafting anything.
        """
        if not question.strip():
            raise ValueError("a question is required")
        if domain not in DISPUTE_DOMAINS:
            raise ValueError(
                f"unknown dispute domain {domain!r}; PROXY routes "
                f"{sorted(DISPUTE_DOMAINS)}"
            )
        report = self.health()
        if report.mode in (CapabilityMode.NOT_CONFIGURED, CapabilityMode.UNAVAILABLE):
            return self.unconfigured_result(gaps=("regulation_answer",))

        payload: dict[str, Any] = {"question": question, "domain": domain}
        if institution_name:
            payload["institution_name"] = institution_name
        try:
            body = self._request("POST", "/ask", payload=payload)
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            return CapabilityResult(
                capability=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                payload={"error": detail},
                observations=(self.missing("regulation_answer", note=detail),),
                gaps=("regulation_answer",),
            )

        answer = ""
        citations: list[str] = []
        if isinstance(body, dict):
            answer = str(body.get("final_answer") or body.get("strategy") or "").strip()
            citations = [
                str(c) for c in (body.get("citations") or []) if str(c).strip()
            ]

        if not answer:
            return CapabilityResult(
                capability=self.name,
                mode=report.mode,
                payload={"domain": domain, "question": question},
                observations=(
                    self.missing(
                        "regulation_answer", note="PROXY returned no answer text"
                    ),
                ),
                gaps=("regulation_answer",),
            )

        citation_obs: tuple[Observation, ...]
        if citations:
            citation_obs = (
                self.observe(
                    "citations",
                    citations,
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note=f"{len(citations)} corpus citation(s)",
                ),
            )
        else:
            citation_obs = (self.missing("verified_citations"),)

        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload={
                "domain": domain,
                "question": question,
                "citation_count": len(citations),
                "requires_human_review": True,
                "artifacts_are_drafts": True,
            },
            observations=(
                self.observe(
                    "regulation_answer",
                    answer,
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note=(
                        "retrieved-and-summarised from PROXY's indexed regulation "
                        "corpus; a summary of a rule is not the rule, and it is "
                        "not legal advice"
                    ),
                    raw_hash=content_hash(answer),
                ),
                *citation_obs,
            ),
            gaps=() if citations else ("verified_citations",),
            subsystem_ref=f"proxy:ask:{content_hash(question)[:12]}",
            confidence=0.4,
        )

    # ------------------------------------------------------------------

    def _request(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self.base_url}{path}"
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"refusing non-http endpoint {url!r}")
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(  # noqa: S310 - scheme checked above
            url, data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
