"""Property intelligence, fronting InHeir.AI (spec Sec. 14, Sec. 21).

InHeir is MIT-licensed and genuinely useful: geocoding, document understanding
via Azure Form Recognizer, a legal knowledge base, and crowdsourced property
reports with a human verification verdict.

**The finding that shapes this whole module.**  InHeir's ``POST /gis/analyze``
returns ten numeric scores -- ``flood_risk``, ``crime_rate``,
``air_quality_index``, ``property_buying_risk`` and so on.  Reading
``routers/gis.py`` shows how they are produced: an Azure OpenAI chat completion
at ``temperature=0.7``, prompted with nothing but the address string, asked to
return JSON.  There is no flood dataset, no crime statistic, no air-quality feed
behind them.

They are a language model's impression of a place.  That is not evidence, and
under Sec. 11 ("NEVER fabricate missing historical data"), Sec. 24 and the
project's own rule that a model may propose but never decide, this adapter must
not launder them into the evidence graph as measurements.

So they are carried, because a human may still want to read them, but:

* every score is marked ``EvidenceClass.UNVERIFIED`` at best and annotated
  ``MODEL-GENERATED``, never ``VERIFIED``;
* the payload states the generator and temperature, so a reviewer sees why;
* ``risk_is_model_generated`` is set on the result, so a policy can refuse it;
* they are never turned into a numeric risk score for the policy engine, because
  ``policy._check_risk`` treats a risk number as advisory input and a fabricated
  one would add false precision to a real decision.

What *is* real and is treated as evidence:

* **coordinates** -- geocoded by OpenCage, a lookup against an actual gazetteer;
* **property reports** -- crowdsourced text carrying a human ``verdict`` of
  ``Verified`` / ``Not Verified`` / ``Pending``, which maps onto our evidence
  classes honestly.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from beacon.assurance.evidence import EvidenceClass, Observation, content_hash

from adapters.base import Capability, CapabilityMode, CapabilityResult, HealthReport

__all__ = ["MODEL_GENERATED_FIELDS", "PropertyAdapter"]


#: The ten fields InHeir produces from an LLM prompt rather than from data.
#: Listed explicitly so a future contributor cannot mistake one for a
#: measurement, and so a test can assert none of them is ever decision-grade.
MODEL_GENERATED_FIELDS: frozenset[str] = frozenset(
    {
        "property_buying_risk",
        "property_renting_risk",
        "flood_risk",
        "crime_rate",
        "air_quality_index",
        "proximity_to_amenities",
        "transportation_score",
        "neighborhood_rating",
        "environmental_hazards",
        "economic_growth_potential",
    }
)

#: InHeir's human verification verdict -> our evidence classes.  A pending
#: report is real text that nobody has checked yet, which is exactly UNVERIFIED;
#: an explicitly rejected one is CONFLICTING, because a human looked and
#: disagreed with the claim rather than finding nothing.
_VERDICT_TO_CLASS = {
    "Verified": EvidenceClass.VERIFIED,
    "Pending": EvidenceClass.UNVERIFIED,
    "Not Verified": EvidenceClass.CONFLICTING,
}

_MODEL_NOTE = (
    "MODEL-GENERATED: produced by an Azure OpenAI completion at temperature=0.7 "
    "from the address string alone, with no underlying flood/crime/air-quality "
    "dataset. Informative for a human reader; not a measurement, and not "
    "grounds for a money decision."
)


class PropertyAdapter(Capability):
    """Location and property evidence from InHeir.AI."""

    name = "property"
    upstream = "InHeir.AI (MIT)"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 20.0,
        mode_override: CapabilityMode | None = None,
    ) -> None:
        # InHeir serves its API under /api/v1 behind nginx.
        self.base_url = (base_url or os.getenv("BEACON_PROPERTY_URL") or "").rstrip("/")
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
                    "no InHeir endpoint configured; it runs on Azure with its own "
                    "MongoDB, Form Recognizer and Azure OpenAI deployment"
                ),
                missing_config=("BEACON_PROPERTY_URL",),
                upstream=self.upstream,
            )
        try:
            self._request("GET", "/report/all")
        except Exception as exc:  # noqa: BLE001 - health must not raise
            return HealthReport(
                name=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                detail=f"{type(exc).__name__}: {exc}",
                endpoint=self.base_url,
                upstream=self.upstream,
            )
        return HealthReport(
            name=self.name,
            mode=CapabilityMode.LIVE,
            detail="InHeir reachable",
            endpoint=self.base_url,
            upstream=self.upstream,
        )

    # ------------------------------------------------------------------
    # location
    # ------------------------------------------------------------------

    def location_intelligence(self, *, address: str) -> CapabilityResult:
        """Geocode an address and carry InHeir's location scores as model output.

        The coordinates are evidence.  The scores are not, and the result says
        so in three places so it cannot be missed.
        """
        if not address.strip():
            raise ValueError("an address is required to analyse a location")
        report = self.health()
        if report.mode in (CapabilityMode.NOT_CONFIGURED, CapabilityMode.UNAVAILABLE):
            return self.unconfigured_result(gaps=("coordinates", "location_risk"))

        try:
            body = self._request("POST", "/gis/analyze", payload={"address": address})
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            return CapabilityResult(
                capability=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                payload={"error": detail, "address": address},
                observations=(
                    self.missing(
                        "coordinates", note=f"InHeir did not answer: {detail}"
                    ),
                ),
                gaps=("coordinates", "location_risk"),
            )

        if not isinstance(body, dict):
            return CapabilityResult(
                capability=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                payload={"error": "InHeir returned a non-object body"},
                observations=(self.missing("coordinates"),),
                gaps=("coordinates", "location_risk"),
            )

        observations: list[Observation] = []
        coordinates = body.get("coordinates")
        if isinstance(coordinates, dict) and coordinates.get("latitude") is not None:
            observations.append(
                self.observe(
                    "coordinates",
                    {
                        "latitude": float(coordinates["latitude"]),
                        "longitude": float(coordinates["longitude"]),
                    },
                    # A gazetteer lookup is a real external fact, but OpenCage is
                    # not the authority on which building the user meant.
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note="geocoded by OpenCage via InHeir",
                    raw_hash=content_hash(coordinates),
                )
            )
        else:
            coordinates = None
            observations.append(
                self.missing(
                    "coordinates", note=f"InHeir could not geocode {address!r}"
                )
            )

        scores = {
            field: body[field]
            for field in sorted(MODEL_GENERATED_FIELDS)
            if body.get(field) is not None
        }
        for field, value in scores.items():
            observations.append(
                self.observe(
                    field,
                    float(value),
                    # Never VERIFIED: there is no dataset behind this number.
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note=_MODEL_NOTE,
                )
            )

        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload={
                "address": address,
                "coordinates": coordinates,
                "location_scores": scores,
                "risk_is_model_generated": bool(scores),
                "risk_generator": (
                    "azure-openai chat completion, temperature=0.7, "
                    "inheir/routers/gis.py"
                ),
                "model_generated_fields": sorted(scores),
            },
            observations=tuple(observations),
            gaps=() if coordinates else ("coordinates",),
            subsystem_ref=f"inheir:address:{content_hash(address)[:12]}",
            # Deliberately modest, and never derived from the scores themselves.
            confidence=0.5 if coordinates else None,
        )

    # ------------------------------------------------------------------
    # reports
    # ------------------------------------------------------------------

    def property_reports(self, *, address: str) -> CapabilityResult:
        """Crowdsourced reports about a property, graded by their human verdict.

        Matching is a normalised exact comparison on the address.  A fuzzy match
        would attach somebody else's property dispute to this transaction, which
        is worse than returning nothing.
        """
        if not address.strip():
            raise ValueError("an address is required to look up reports")
        report = self.health()
        if report.mode in (CapabilityMode.NOT_CONFIGURED, CapabilityMode.UNAVAILABLE):
            return self.unconfigured_result(gaps=("property_reports",))

        try:
            rows = self._request("GET", "/report/all")
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            return CapabilityResult(
                capability=self.name,
                mode=CapabilityMode.UNAVAILABLE,
                payload={"error": detail},
                observations=(self.missing("property_reports", note=detail),),
                gaps=("property_reports",),
            )

        searched = rows if isinstance(rows, list) else []
        needle = _normalise(address)
        matches = [
            row
            for row in searched
            if isinstance(row, dict)
            and _normalise(str(row.get("address", ""))) == needle
        ]
        if not matches:
            return CapabilityResult(
                capability=self.name,
                mode=report.mode,
                payload={
                    "address": address,
                    "match_count": 0,
                    "searched": len(searched),
                    "note": (
                        "no report filed for this address; absence of a report is "
                        "not evidence that the property is sound"
                    ),
                },
                observations=(
                    self.missing(
                        "property_reports",
                        note=f"no crowdsourced report matches {address!r}",
                    ),
                ),
                gaps=("property_reports",),
            )

        observations = tuple(
            self.observe(
                "property_report",
                {
                    "verdict": str(row.get("verdict") or "Pending"),
                    "report": str(row.get("report") or ""),
                    "reason": row.get("reason"),
                },
                evidence_class=_VERDICT_TO_CLASS.get(
                    str(row.get("verdict") or "Pending"), EvidenceClass.UNVERIFIED
                ),
                note=f"crowdsourced report, human verdict={row.get('verdict')!r}",
                raw_hash=content_hash(row),
            )
            for row in matches
        )
        verdicts = sorted({str(r.get("verdict") or "Pending") for r in matches})
        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload={
                "address": address,
                "match_count": len(matches),
                "verdicts": verdicts,
                "has_verified_concern": "Verified" in verdicts,
            },
            observations=observations,
            gaps=(),
            subsystem_ref=f"inheir:reports:{content_hash(address)[:12]}",
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


def _normalise(address: str) -> str:
    """Lowercase, collapse whitespace, drop punctuation that varies by typist."""
    stripped = "".join(c if c.isalnum() or c.isspace() else " " for c in address)
    return " ".join(stripped.lower().split())
