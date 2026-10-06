"""Capture actual GreenChain /score processing on explicit reference inputs.

Run from the root in an environment with GreenChain's score dependencies.
This uses the preserved app's native function; it copies no implementation.
Supplier verification/networking is disabled for fictitious .example inputs.
The resulting replay remains reference data and never stands in for /search.
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


def capture() -> dict:
    folder = Path(__file__).resolve().parent
    root = folder.parents[1]
    project = root / "GREENCHAIN-main" / "greenchain"
    os.environ["ML_ROOT"] = str(project / "backend" / "ml_runtime")
    sys.path.insert(0, str(project))
    # The preserved project's import root is selected above at runtime.
    from backend import ml_scorer  # type: ignore[import-not-found]

    original_verifier = ml_scorer.verify_all
    def reference_verification(rows: list[dict]) -> None:
        for row in rows:
            row["verification"] = {"registry_match": None, "source_count": 0, "domain_age_days": None,
                                   "domain_flag": False, "confidence": "unverified", "reference_only": True}
    ml_scorer.verify_all = reference_verification
    inputs = json.loads((folder / "greenchain_input.json").read_text(encoding="utf-8"))
    try:
        results = ml_scorer.compute_composite_scores(deepcopy(inputs["manufacturers"]), transport_mode=inputs["transport_mode"])
    finally:
        ml_scorer.verify_all = original_verifier
    native_path = project / "backend" / "ml_scorer.py"
    return {
        "capture": {"mode": "reference", "synthetic_inputs": True, "native_function": "backend.ml_scorer.compute_composite_scores",
                    "native_source_sha256": sha256(native_path.read_bytes()).hexdigest(),
                    "captured_at": datetime.now(timezone.utc).isoformat(), "discovery_performed": False,
                    "verification_performed": False, "description": "Actual native /score function on fictitious inputs; replayed as a /search-shaped reference envelope only."},
        "response": {"product": "ergonomic office chairs", "destination": "IN", "transport_mode": "road", "countries": ["IN"],
                     "duration_seconds": 0, "count": len(results), "results": results, "cache_hits": 0, "fallback_components": []},
    }


if __name__ == "__main__":
    output = capture()
    Path(__file__).with_name("greenchain_native.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Captured native GreenChain scoring of 3 fictitious suppliers; no supplier discovery or verification.")
