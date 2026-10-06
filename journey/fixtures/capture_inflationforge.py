"""Capture read-only native InflationForge endpoints using a temporary DB.

The existing bundled snapshot is replayed as historical data. No live sync,
source fetch, original database write, price conversion or chair quote occurs.
"""

from __future__ import annotations

import json
import gc
import os
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory


def capture() -> dict:
    folder = Path(__file__).resolve().parent
    root = folder.parents[1]
    project = root / "Inflation-Forge-main"
    sys.path.insert(0, str(project))
    os.environ["INFLATIONFORGE_OTEL_EXPORTER"] = "none"
    # The preserved project's import root is selected above at runtime.
    from backend.config import Settings  # type: ignore[import-not-found]
    from backend.services.inflation.service import InflationForgeService  # type: ignore[import-not-found]

    with TemporaryDirectory(prefix="peoplepay-inflation-capture-") as temporary:
        temp = Path(temporary)
        (temp / "data").mkdir()
        snapshot_path = project / "data" / "bootstrap_snapshot.json"
        (temp / "data" / "bootstrap_snapshot.json").write_bytes(snapshot_path.read_bytes())
        service = InflationForgeService(Settings(root=temp, db_path=temp / "capture.sqlite3", otel_mode="none"))
        # These are exactly the values the read-only /api/items, /api/snapshots,
        # /api/snapshots/{id}/observations handlers serialize.
        items = [item.model_dump(mode="json") for item in service.factory.list(include_retired=False)]
        snapshots = service.db.list("price_snapshot", limit=50)
        snapshot = snapshots[0]
        observations = [row for row in service.db.list("price_observation", parent_id=snapshot["id"], limit=1000)
                        if row["item_id"] == "milk-gallon" and row["city_id"] == "chicago"]
        result = {"capture": {"mode": "reference", "captured_at": datetime.now(timezone.utc).isoformat(),
                             "native_source": "backend.services.inflation.service.InflationForgeService",
                             "snapshot_file_sha256": sha256(snapshot_path.read_bytes()).hexdigest(),
                             "native_source_sha256": sha256((project / "backend" / "services" / "inflation" / "service.py").read_bytes()).hexdigest(),
                             "live_sync_performed": False, "description": "Native bootstrap/service output from a disposable DB; prices remain the bundled historical USD city observations."},
                "items": items, "snapshot": snapshot, "observations": observations}
        # The native Database context commits but does not explicitly close
        # SQLite connections. Collect expired handles before Windows cleanup.
        del service
        gc.collect()
        return result


if __name__ == "__main__":
    output = capture()
    Path(__file__).with_name("inflationforge_native.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Captured native InflationForge service outputs from temporary DB; no chair quote or live refresh.")
