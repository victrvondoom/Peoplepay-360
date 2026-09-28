"""Shared fixtures for the integration-layer tests.

Everything here is offline and deterministic.  The adapters are exercised
against pinned modes rather than a live upstream, because a suite that needs
InflationForge running is a suite that fails for reasons unrelated to the code
under test.  The live checks against the real services were run separately and
are recorded in the commit history.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Beacon's package lives under Beacon-main/src; the integration layer sits at the
# repository root.  Both go on the path here rather than in every test file.
_ROOT = Path(__file__).resolve().parent.parent
for entry in (str(_ROOT), str(_ROOT / "Beacon-main" / "src")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from adapters.base import (  # noqa: E402
    Capability,
    CapabilityMode,
    CapabilityResult,
    HealthReport,
)


@pytest.fixture
def sample_room() -> dict[str, Any]:
    """Rumi's own ``sampleRoom``, copied as *data* from its fixture.

    Values only -- no Rumi source.  ``rumi-main`` is unlicensed, so nothing of
    its implementation may be vendored (see docs/licensing-blockers.md); a room's
    measurements passed over a boundary are the interface, not the expression.
    """
    return {
        "id": "bedroom-demo",
        "name": "A quieter kind of bedroom",
        "revision": 0,
        "shape": "rectangle",
        "dimensions": {"width": 4.8, "height": 2.7, "depth": 4.2},
        "measurementSource": "confirmed",
        "openings": [
            {
                "id": "door",
                "kind": "door",
                "wall": "south",
                "offset": 0.25,
                "width": 0.9,
                "height": 2.1,
                "sill": 0,
            },
            {
                "id": "window",
                "kind": "window",
                "wall": "north",
                "offset": 2.7,
                "width": 1.4,
                "height": 1.2,
                "sill": 1,
            },
        ],
        "objects": [
            {
                "id": "owned-bed",
                "name": "Your bed",
                "category": "bed",
                "productId": None,
                "dimensions": {"width": 1.6, "height": 0.6, "depth": 2.1},
                "owned": True,
                "locked": True,
            },
        ],
    }


@pytest.fixture
def usd_brief() -> dict[str, Any]:
    """A Rumi brief.  USD, because Rumi's schema hard-locks that currency."""
    return {"budgetCents": 80_000_00, "currency": "USD", "prompt": "a study setup"}


class StubCapability(Capability):
    """A capability whose mode and payload the test dictates.

    Used to prove the *bridge and gateway* behaviour for each mode without
    depending on any upstream being reachable.
    """

    name = "market"
    upstream = "stub"

    def __init__(
        self,
        mode: CapabilityMode = CapabilityMode.LIVE,
        *,
        name: str = "market",
        raises: bool = False,
    ) -> None:
        self.name = name
        self._mode = mode
        self._raises = raises

    def health(self) -> HealthReport:
        if self._raises:
            raise RuntimeError("health check exploded")
        return HealthReport(name=self.name, mode=self._mode, detail="stub")

    def price_evidence(
        self, *, item_query: str, city_id: str | None = None
    ) -> CapabilityResult:
        if self._mode in (CapabilityMode.NOT_CONFIGURED, CapabilityMode.UNAVAILABLE):
            return self.unconfigured_result(gaps=("observed_price",))
        return CapabilityResult(
            capability=self.name,
            mode=self._mode,
            payload={"item_query": item_query, "row_count": 3},
            observations=(
                self.observe(
                    "observed_price",
                    {"minor": 7_850_000, "currency": "INR"},
                    note="stubbed",
                ),
            ),
            subsystem_ref="stub:snapshot:1",
        )


@pytest.fixture
def stub_capability() -> type[StubCapability]:
    return StubCapability
