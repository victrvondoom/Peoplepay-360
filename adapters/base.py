"""What every capability adapter must be, and how it must tell the truth.

Spec Sec. 24 and Sec. 25 are the whole design of this module: an adapter whose
dependency is missing does **not** fake a successful answer.  It reports its
mode, and the transaction records the gap as ``UNAVAILABLE`` /
``NOT_CONFIGURED`` rather than a plausible-looking value.

The five modes are distinct because the UI has to distinguish them:

    LIVE            talking to the real provider
    SANDBOX         a real provider's test mode, or a local sandbox
    MOCK            fixture data, for tests only
    NOT_CONFIGURED  we have an adapter, but no credentials/endpoint
    UNAVAILABLE     configured, but the provider did not answer

``SANDBOX`` and ``MOCK`` both mark their evidence with
``Provenance(sandbox=True)``, which ``Observation.__post_init__`` then forces to
``EvidenceClass.SANDBOX`` -- so sandbox data cannot launder itself into a real
purchase decision no matter what an adapter claims.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from beacon.assurance.evidence import (
    EvidenceClass,
    Observation,
    Provenance,
    unavailable,
    utcnow,
)

__all__ = [
    "Capability",
    "CapabilityError",
    "CapabilityMode",
    "CapabilityResult",
    "HealthReport",
]


class CapabilityMode(StrEnum):
    LIVE = "LIVE"
    SANDBOX = "SANDBOX"
    MOCK = "MOCK"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"


#: Modes whose output may back a real-money decision.
_REAL_MODES = frozenset({CapabilityMode.LIVE})

#: Modes that mark their evidence as sandbox-derived.
_SANDBOX_MODES = frozenset({CapabilityMode.SANDBOX, CapabilityMode.MOCK})


class CapabilityError(RuntimeError):
    """Raised when a capability cannot do what was asked.

    Carrying the mode means the caller can distinguish "not set up" from
    "set up and broken" without parsing a message.
    """

    def __init__(self, capability: str, mode: CapabilityMode, detail: str) -> None:
        self.capability = capability
        self.mode = mode
        self.detail = detail
        super().__init__(f"{capability} [{mode}]: {detail}")


@dataclass(frozen=True, slots=True)
class HealthReport:
    """One line of ``/health/integrations`` (spec Sec. 25)."""

    name: str
    mode: CapabilityMode
    detail: str = ""
    checked_at: str = field(default_factory=lambda: utcnow().isoformat())
    endpoint: str | None = None
    missing_config: tuple[str, ...] = ()
    upstream: str = ""

    @property
    def usable(self) -> bool:
        return self.mode in (
            CapabilityMode.LIVE,
            CapabilityMode.SANDBOX,
            CapabilityMode.MOCK,
        )

    @property
    def decision_grade(self) -> bool:
        """True only when this capability may back a real-money decision."""
        return self.mode in _REAL_MODES

    def to_dict(self, *, include_endpoint: bool = False) -> dict[str, Any]:
        """Serialize for a health payload.

        ``endpoint`` is withheld by default.  ``/health/integrations`` is
        deliberately unauthenticated so an operator can reach it during an
        incident, which means anything in it is public -- and an internal
        hostname such as ``http://internal-market.svc:8010`` is a map of the
        private network handed to whoever asks.  Callers that are already behind
        the auth check pass ``include_endpoint=True``.

        ``endpoint_configured`` still answers the question an operator actually
        has ("is this wired up at all?") without naming the host.
        """
        body = {
            "name": self.name,
            "mode": str(self.mode),
            "detail": self.detail,
            "checked_at": self.checked_at,
            "endpoint_configured": self.endpoint is not None,
            "missing_config": list(self.missing_config),
            "upstream": self.upstream,
            "usable": self.usable,
            "decision_grade": self.decision_grade,
        }
        if include_endpoint:
            body["endpoint"] = self.endpoint
        return body


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """What a capability returns: data, its mode, and what it could not get.

    ``gaps`` is never inferred later -- the adapter names its own gaps, because
    only it knows what it asked the provider for.
    """

    capability: str
    mode: CapabilityMode
    payload: dict[str, Any] = field(default_factory=dict)
    observations: tuple[Observation, ...] = ()
    gaps: tuple[str, ...] = ()
    subsystem_ref: str | None = None
    confidence: float | None = None

    @property
    def is_sandbox(self) -> bool:
        return self.mode in _SANDBOX_MODES

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "mode": str(self.mode),
            "payload": self.payload,
            "observations": [o.to_dict() for o in self.observations],
            "gaps": list(self.gaps),
            "subsystem_ref": self.subsystem_ref,
            "confidence": self.confidence,
            "sandbox": self.is_sandbox,
        }


class Capability(ABC):
    """Base class for every subsystem adapter.

    Subclasses implement :meth:`health` and whatever domain calls they offer.
    The helpers here exist so that no adapter has to hand-roll provenance and
    accidentally omit the sandbox flag.
    """

    #: Stable name used in health output, evidence provenance and the event bus.
    name: str = "capability"

    #: Which upstream project this adapter fronts, for attribution (Sec. 36).
    upstream: str = ""

    @abstractmethod
    def health(self) -> HealthReport:
        """Report the current mode.  Must never raise."""

    # --- provenance helpers -------------------------------------------

    def provenance(
        self,
        *,
        source_url: str | None = None,
        raw_reference: str | None = None,
        raw_hash: str | None = None,
        mode: CapabilityMode | None = None,
    ) -> Provenance:
        """Build provenance that is honest about this adapter's mode."""
        effective = mode or self.health().mode
        return Provenance(
            source=self.name,
            retrieved_at=utcnow(),
            source_url=source_url,
            raw_reference=raw_reference,
            raw_hash=raw_hash,
            adapter=f"{self.name}->{self.upstream}" if self.upstream else self.name,
            sandbox=effective in _SANDBOX_MODES,
        )

    def observe(
        self,
        field_name: str,
        value: Any,
        *,
        evidence_class: EvidenceClass = EvidenceClass.UNVERIFIED,
        note: str = "",
        normalized_value: Any = None,
        source_url: str | None = None,
        raw_reference: str | None = None,
        raw_hash: str | None = None,
        mode: CapabilityMode | None = None,
    ) -> Observation:
        """One observed fact with provenance attached.

        A sandbox mode downgrades the class automatically inside
        ``Observation``; we do not have to remember to do it here.
        """
        return Observation(
            field=field_name,
            value=value,
            provenance=self.provenance(
                source_url=source_url,
                raw_reference=raw_reference,
                raw_hash=raw_hash,
                mode=mode,
            ),
            evidence_class=evidence_class,
            normalized_value=normalized_value,
            note=note,
        )

    def missing(self, field_name: str, *, note: str = "") -> Observation:
        """The honest answer when the provider had nothing for us."""
        report = self.health()
        return unavailable(
            field_name,
            self.name,
            note=note or f"{self.name} mode={report.mode}: {report.detail}".strip(),
            sandbox=report.mode in _SANDBOX_MODES,
        )

    def unconfigured_result(self, *, gaps: tuple[str, ...] = ()) -> CapabilityResult:
        """The result an adapter returns when it has no provider at all.

        Returning this -- rather than raising or inventing data -- is what lets
        the orchestrator continue a transaction with an explicit hole in it.
        """
        report = self.health()
        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload={
                "detail": report.detail,
                "missing_config": list(report.missing_config),
            },
            observations=tuple(self.missing(g) for g in gaps),
            gaps=gaps,
        )
