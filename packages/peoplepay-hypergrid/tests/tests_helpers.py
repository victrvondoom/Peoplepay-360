def calls(cid):
    from peoplepay_models.adapters import mock as mm
    return mm._STATE.get(cid, {}).get("calls", 0)
