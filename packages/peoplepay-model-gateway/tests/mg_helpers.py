FAST = {"id": "m-fast", "name": "Fast", "context": 32000}
VISION = {"id": "m-vision", "name": "Vision", "vision": True, "tools": True, "context": 64000}
DEEP = {"id": "m-deep", "name": "Deep", "reasoning": True, "vision": True, "tools": True, "structured": True, "context": 200000}


def add_mock(gw, owner, name, models=None, **cfg):
    out = gw.connect(owner, "mock", name, {"models": models or [FAST], **cfg})
    return out["connection"]["id"]


def calls(cid):
    """Generation calls received by a mock connection (0 if it never generated)."""
    from peoplepay_models.adapters import mock as mm
    return mm._STATE.get(cid, {}).get("calls", 0)
