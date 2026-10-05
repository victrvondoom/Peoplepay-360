"""
ml_bridge.py
------------
Adds the external `machine_learning/` directory to sys.path so backend modules
can `from ml.inference import EmissionsModel, TransportCalculator, ScoreAssembler`.

The ML code lives outside the backend package (see ML_ROOT in .env). This
module performs the path wiring once; import it before anything else that
pulls from `ml.*`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).parent / ".env")


def _resolve_ml_root() -> Path:
    env = os.environ.get("ML_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p
    # Fallback 1: vendored copy at backend/ml_runtime/ (default for clone-and-run).
    vendored = (Path(__file__).parent / "ml_runtime").resolve()
    if vendored.exists():
        return vendored
    # Fallback 2: external machine_learning/ directory (dev setup).
    guess = (Path(__file__).parent / ".." / "machine_learning").resolve()
    return guess


ML_ROOT = _resolve_ml_root()

if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))


# Lazy singletons so FastAPI startup cost is one-shot.
_emissions_model = None


def get_emissions_model():
    """Return a cached EmissionsModel instance (loads XGBoost joblibs once)."""
    global _emissions_model
    if _emissions_model is None:
        from ml.inference import EmissionsModel  # type: ignore

        _emissions_model = EmissionsModel.load()
    return _emissions_model


def get_transport_calculator():
    from ml.inference import TransportCalculator  # type: ignore

    return TransportCalculator


def get_score_assembler():
    from ml.inference import ScoreAssembler  # type: ignore

    return ScoreAssembler


__all__ = [
    "ML_ROOT",
    "get_emissions_model",
    "get_transport_calculator",
    "get_score_assembler",
]
