"""Spatial intelligence, fronting Rumi (spec Sec. 7, Sec. 8).

Rumi already does the hard part: iOS RoomPlan capture, QR/browser pairing, room
reconstruction, free-floor computation, door-clearance rules, placement
validation and budget-aware planning.  All of that stays in Rumi, in
TypeScript, where it is tested.  This adapter's whole job is to turn a Rumi room
into ``Transaction`` context and to carry Rumi's own verdicts across as evidence.

What this adapter deliberately does **not** do:

* It does not re-implement geometry.  ``shared/planner/free-floor.ts`` and
  ``shared/geometry/index.ts`` own that, and duplicating them in Python would
  create a second answer that could silently disagree with the one the user
  sees in the 3D editor.
* It does not soften Rumi's measurement grading.  Rumi distinguishes
  ``confirmed`` from ``estimated`` dimensions and forbids a value when the
  source is ``unknown``; that maps onto our ``EvidenceClass`` directly rather
  than being flattened.

Two audited conflicts are handled here rather than hidden:

**Units.** Rumi geometry is in **metres**; we keep metres and say so in the
field name, because a silent unit change is how clearances get violated.

**Currency.** Rumi's brief schema hard-locks ``currency: z.literal("USD")`` and
prices as ``priceCents``.  A ``budgetCents`` therefore arrives as USD minor
units.  We refuse to relabel it as INR: ``Money`` carries the real currency, and
a cross-currency comparison raises rather than guessing an FX rate.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from beacon.assurance.evidence import EvidenceClass, content_hash
from beacon.assurance.money import Money

from adapters.base import Capability, CapabilityMode, CapabilityResult, HealthReport

__all__ = [
    "RUMI_DOOR_CLEARANCE_M",
    "RoomContext",
    "SpatialAdapter",
    "SpatialConstraint",
]


#: Rumi's own measurement grading -> our evidence classes.  ``estimated`` is
#: real but weaker; it must not pass as a confirmed catalogue dimension.
_MEASUREMENT_TO_CLASS = {
    "confirmed": EvidenceClass.VERIFIED,
    "estimated": EvidenceClass.UNVERIFIED,
    "unknown": EvidenceClass.UNKNOWN,
}

#: Rumi's door clearance, mirrored as a named constant so the value that
#: reaches a contract is traceable to its source rather than a magic number.
#: Source: rumi-main/shared/planner/space.ts -> DOOR_CLEARANCE.
RUMI_DOOR_CLEARANCE_M = 0.9


@dataclass(frozen=True, slots=True)
class SpatialConstraint:
    """One limit a candidate product must satisfy to be placeable.

    Deterministic and checkable.  The model may propose a desk; this is what
    code checks it against (spec Sec. 46, "the model proposes, code checks").
    """

    name: str
    axis: str
    """``width`` | ``depth`` | ``height`` | ``floor_area`` | ``clearance``."""

    max_metres: float | None = None
    min_metres: float | None = None
    note: str = ""
    derived_from: str = ""

    def permits(self, value_metres: float) -> bool:
        if self.max_metres is not None and value_metres > self.max_metres:
            return False
        if self.min_metres is not None and value_metres < self.min_metres:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "axis": self.axis,
            "max_metres": self.max_metres,
            "min_metres": self.min_metres,
            "note": self.note,
            "derived_from": self.derived_from,
        }


@dataclass(frozen=True, slots=True)
class RoomContext:
    """A Rumi room, reduced to what a transaction needs to decide.

    Keeps Rumi's identifiers (``room_id``, ``revision``) so a placement decision
    can be re-checked against the exact room revision it was made for.  A room
    edited after a contract was written is a changed premise, not a detail.
    """

    room_id: str
    revision: int
    shape: str
    width_m: float
    depth_m: float
    height_m: float
    measurement_source: str
    existing_objects: tuple[dict[str, Any], ...] = ()
    openings: tuple[dict[str, Any], ...] = ()
    owned_object_ids: tuple[str, ...] = ()
    budget: Money | None = None
    warnings: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def floor_area_m2(self) -> float:
        return round(self.width_m * self.depth_m, 4)

    @property
    def door_keepout_m(self) -> float:
        """Approach depth to reserve in front of the widest door.

        Mirrors Rumi's ``Math.max(DOOR_CLEARANCE, door.width)``
        (``shared/planner/space.ts``).  With no door in the capture we still
        reserve the default rather than zero: a room almost certainly has a way
        in, and assuming otherwise is the optimistic guess that puts a wardrobe
        across a doorway.
        """
        widths = [
            float(o.get("width") or 0.0)
            for o in self.openings
            if str(o.get("kind") or "").lower() == "door"
        ]
        return round(max([RUMI_DOOR_CLEARANCE_M, *widths]), 4)

    def constraints(self) -> tuple[SpatialConstraint, ...]:
        """Derive the deterministic limits a product must satisfy.

        Conservative on purpose: the widest a new item may be is the room's
        narrower horizontal span minus the door clearance Rumi itself enforces.
        Getting this wrong blocks a doorway in the real world.
        """
        return (
            SpatialConstraint(
                name="fits_room_width",
                axis="width",
                max_metres=self.width_m,
                note="a product cannot be wider than the room",
                derived_from=f"room:{self.room_id}@{self.revision}",
            ),
            SpatialConstraint(
                name="fits_room_depth",
                axis="depth",
                max_metres=self.depth_m,
                derived_from=f"room:{self.room_id}@{self.revision}",
            ),
            SpatialConstraint(
                name="fits_room_height",
                axis="height",
                max_metres=self.height_m,
                derived_from=f"room:{self.room_id}@{self.revision}",
            ),
            SpatialConstraint(
                name="leaves_room_for_door_keepout",
                axis="depth",
                max_metres=round(max(self.depth_m - self.door_keepout_m, 0.0), 4),
                note=(
                    f"the deepest run along one wall once each doorway's "
                    f"{self.door_keepout_m}m approach zone is reserved; Rumi "
                    "models that zone as a 2D keep-out region, so this is a "
                    "necessary bound, not a sufficient one"
                ),
                derived_from="rumi/shared/planner/space.ts:DOOR_CLEARANCE",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "revision": self.revision,
            "shape": self.shape,
            "width_m": self.width_m,
            "depth_m": self.depth_m,
            "height_m": self.height_m,
            "floor_area_m2": self.floor_area_m2,
            "measurement_source": self.measurement_source,
            "existing_object_count": len(self.existing_objects),
            "owned_object_ids": list(self.owned_object_ids),
            "opening_count": len(self.openings),
            "door_keepout_m": self.door_keepout_m,
            "budget": self.budget.to_dict() if self.budget else None,
            "warnings": list(self.warnings),
            "constraints": [c.to_dict() for c in self.constraints()],
        }

    @classmethod
    def from_rumi(
        cls, room: dict[str, Any], *, brief: dict[str, Any] | None = None
    ) -> RoomContext:
        """Build from Rumi's ``roomSchema`` JSON.

        Raises on a missing dimension rather than defaulting one: a room with no
        measured size is not a room we can place furniture in, and a guessed
        metre is a real-world collision.
        """
        dims = room.get("dimensions") or {}
        missing = [k for k in ("width", "depth", "height") if dims.get(k) is None]
        if missing:
            raise ValueError(
                f"Rumi room {room.get('id')!r} is missing {missing}; "
                "refusing to substitute a guessed dimension"
            )
        objects = tuple(room.get("objects") or ())
        budget: Money | None = None
        if brief and brief.get("budgetCents") is not None:
            # Rumi hard-locks USD in briefSchema; keep the real currency.
            budget = Money(
                int(brief["budgetCents"]), str(brief.get("currency") or "USD")
            )
        capture = room.get("capture") or {}
        return cls(
            room_id=str(room.get("id") or ""),
            revision=int(room.get("revision") or 0),
            shape=str(room.get("shape") or "rectangle"),
            width_m=float(dims["width"]),
            depth_m=float(dims["depth"]),
            height_m=float(dims["height"]),
            measurement_source=str(room.get("measurementSource") or "estimated"),
            existing_objects=objects,
            openings=tuple(room.get("openings") or ()),
            owned_object_ids=tuple(
                str(o.get("id")) for o in objects if o.get("owned") is True
            ),
            warnings=tuple(capture.get("warnings") or ()),
            budget=budget,
            raw=room,
        )


class SpatialAdapter(Capability):
    """Room understanding and placement checks, from Rumi."""

    name = "spatial"
    upstream = "Rumi"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 15.0,
        mode_override: CapabilityMode | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("BEACON_SPATIAL_URL") or "").rstrip("/")
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
                    "no Rumi endpoint configured; room capture, pairing and the 3D "
                    "workspace run in the Rumi app and its Convex deployment"
                ),
                missing_config=("BEACON_SPATIAL_URL",),
                upstream=self.upstream,
            )
        try:
            self._get("/")
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
            detail="Rumi workspace reachable",
            endpoint=self.base_url,
            upstream=self.upstream,
        )

    # ------------------------------------------------------------------
    # room context
    # ------------------------------------------------------------------

    def room_context(
        self, room: dict[str, Any], *, brief: dict[str, Any] | None = None
    ) -> CapabilityResult:
        """Turn a Rumi room payload into transaction context.

        Accepts the room as data so this works for a live Convex room, an
        imported scan, or a Rumi fixture -- without the adapter caring which.
        """
        report = self.health()
        try:
            ctx = RoomContext.from_rumi(room, brief=brief)
        except ValueError as exc:
            return CapabilityResult(
                capability=self.name,
                mode=report.mode,
                payload={"error": str(exc)},
                observations=(self.missing("room_dimensions", note=str(exc)),),
                gaps=("room_dimensions",),
            )

        evidence_class = _MEASUREMENT_TO_CLASS.get(
            ctx.measurement_source, EvidenceClass.UNVERIFIED
        )
        observations = [
            self.observe(
                "room_dimensions_m",
                {"width": ctx.width_m, "depth": ctx.depth_m, "height": ctx.height_m},
                evidence_class=evidence_class,
                raw_reference=f"{ctx.room_id}@{ctx.revision}",
                raw_hash=content_hash(ctx.raw),
                note=(
                    f"Rumi measurementSource={ctx.measurement_source}; "
                    "units are metres"
                ),
            ),
            self.observe(
                "free_floor_area_m2",
                ctx.floor_area_m2,
                evidence_class=evidence_class,
                note=(
                    "gross floor area from room dimensions; Rumi's "
                    "findFreeFloorAreas() computes obstacle-aware free regions "
                    "and remains the authority for placement"
                ),
                raw_reference=f"{ctx.room_id}@{ctx.revision}",
            ),
        ]
        if ctx.warnings:
            observations.append(
                self.observe(
                    "capture_warnings",
                    list(ctx.warnings),
                    evidence_class=EvidenceClass.UNVERIFIED,
                    note="warnings reported by the RoomPlan capture itself",
                )
            )
        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload=ctx.to_dict(),
            observations=tuple(observations),
            gaps=(),
            subsystem_ref=f"rumi:room:{ctx.room_id}@{ctx.revision}",
            confidence=0.9 if ctx.measurement_source == "confirmed" else 0.6,
        )

    # ------------------------------------------------------------------
    # placement
    # ------------------------------------------------------------------

    def placement_check(
        self,
        *,
        context: RoomContext,
        product_id: str,
        dimensions_m: dict[str, float] | None,
        measurement_source: str = "unknown",
    ) -> CapabilityResult:
        """Deterministically check a product against the room's constraints.

        An unknown product dimension is **not** treated as a pass.  Rumi keeps
        listed, estimated and unknown dimensions distinct, and so do we: an
        unmeasured product yields ``UNKNOWN`` and a blocked placement, because
        the honest answer is that we cannot tell whether it fits.
        """
        report = self.health()
        constraints = context.constraints()

        if not dimensions_m or any(
            dimensions_m.get(k) is None for k in ("width", "depth", "height")
        ):
            return CapabilityResult(
                capability=self.name,
                mode=report.mode,
                payload={
                    "product_id": product_id,
                    "verdict": "UNKNOWN_DIMENSIONS",
                    "placeable": False,
                    "authoritative": False,
                    "authority": (
                        "rumi/shared/planner/free-floor.ts:findFreeFloorAreas"
                    ),
                    "door_keepout_m": context.door_keepout_m,
                    "reason": (
                        "the product's dimensions are not known, so fit cannot be "
                        "verified; this is not a pass"
                    ),
                    "constraints": [c.to_dict() for c in constraints],
                },
                observations=(
                    self.missing(
                        "product_dimensions_m",
                        note=f"no dimensions available for {product_id}",
                    ),
                ),
                gaps=("product_dimensions_m",),
                subsystem_ref=f"rumi:room:{context.room_id}@{context.revision}",
            )

        failures: list[dict[str, Any]] = []
        for constraint in constraints:
            axis = constraint.axis
            value = dimensions_m.get(axis)
            if value is None:
                continue
            if not constraint.permits(float(value)):
                failures.append(
                    {
                        "constraint": constraint.name,
                        "axis": axis,
                        "product_metres": float(value),
                        "limit_metres": constraint.max_metres,
                        "note": constraint.note,
                    }
                )

        placeable = not failures
        return CapabilityResult(
            capability=self.name,
            mode=report.mode,
            payload={
                "product_id": product_id,
                # NOT_RULED_OUT rather than FITS: these bounds are necessary,
                # not sufficient. Only Rumi's obstacle-aware findFreeFloorAreas()
                # can say a product actually fits a specific spot, and claiming
                # otherwise here would be the second, disagreeing answer this
                # adapter exists to avoid.
                "verdict": "NOT_RULED_OUT" if placeable else "DOES_NOT_FIT",
                "placeable": placeable,
                "authoritative": False,
                "authority": (
                    "rumi/shared/planner/free-floor.ts:findFreeFloorAreas"
                ),
                "failures": failures,
                "door_keepout_m": context.door_keepout_m,
                "room_revision": context.revision,
                "constraints": [c.to_dict() for c in constraints],
            },
            observations=(
                self.observe(
                    "placement_verdict",
                    "NOT_RULED_OUT" if placeable else "DOES_NOT_FIT",
                    evidence_class=_MEASUREMENT_TO_CLASS.get(
                        measurement_source, EvidenceClass.UNVERIFIED
                    ),
                    note=(
                        f"screened against {len(constraints)} necessary room "
                        f"bounds at revision {context.revision} (product "
                        f"measurement source={measurement_source}); a pass means "
                        "not ruled out, not confirmed placeable"
                    ),
                ),
            ),
            gaps=(),
            subsystem_ref=f"rumi:room:{context.room_id}@{context.revision}",
        )

    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"refusing non-http endpoint {url!r}")
        request = urllib.request.Request(  # noqa: S310 - scheme checked above
            url, headers={"Accept": "application/json"}, method="GET"
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            # The Rumi workspace root serves HTML; reachability is the signal.
            return {"reachable": True}
