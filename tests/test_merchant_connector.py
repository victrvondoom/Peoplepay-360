"""Merchant lifecycle, durable authorization binding and safe retries."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from gateway.merchant import IdempotencyConflict, ReferenceMerchant, terms_hash


def action(merchant, version=1, **overrides):
    approved = merchant.quote("supplier-b", "chair-b", 300, 200000000, 30)
    return {"action_id": f"approval-{version}", "actor_id": "procurement-reviewer",
            "transaction_id": "txn-chairs", "decision_id": "decision-chairs",
            "decision_version": version, "decision_hash": str(version) * 64,
            "terms": approved, "terms_hash": terms_hash(approved),
            "mode": "reference", "money_moved": False, **overrides}


def test_another_worker_cannot_create_second_order_for_same_gateway_transaction(tmp_path):
    path = tmp_path / "one-order.sqlite3"
    first, second = ReferenceMerchant(path), ReferenceMerchant(path)
    try:
        approved = action(first)
        session = first.create_session(approved, "create-first", "req-1")
        order = first.complete_session(session["id"], approved, "complete-first", "req-2")
        revised = action(second, version=2, decision_id="another-decision")
        new_session = second.create_session(revised, "create-second", "req-3")
        with pytest.raises(ValueError, match="already has a merchant order"):
            second.complete_session(new_session["id"], revised, "complete-second", "req-4")
        assert second.get_order(order["external_order_ref"])["decision_version"] == 1
    finally:
        first.close()
        second.close()


def completed(merchant):
    approved = action(merchant)
    session = merchant.create_session(approved, "create-1", "request-create")
    return merchant.complete_session(session["id"], approved, "complete-1", "request-complete")


def test_authoritative_order_and_partial_delivery_survive_restart(tmp_path):
    path = tmp_path / "reference.sqlite3"
    merchant = ReferenceMerchant(path)
    checkout = completed(merchant)
    assert checkout["status"] == "completed"
    assert checkout["terms"]["total_minor"] == 177000000
    assert checkout["order"]["money_moved"] is False
    order_ref = checkout["external_order_ref"]
    delivery = merchant.record_delivery(order_ref, 260, "delivery-1", "request-delivery",
                                        note="Final receipt records 260 chairs")
    assert delivery["discrepancy"] is True
    assert delivery["missing_quantity"] == 40
    assert delivery["event"]["event_type"] == "order.delivery_discrepancy"
    assert delivery["event"]["data"]["merchant_order_reference"] == order_ref
    merchant.close()
    restarted = ReferenceMerchant(path)
    assert restarted.get_order(order_ref)["status"] == "DELIVERY_DISCREPANCY"
    assert restarted.get_session(checkout["id"])["status"] == "completed"
    assert len(restarted.get_events(order_ref)) == 2
    replay = restarted.record_delivery(order_ref, 260, "delivery-1", "request-retry",
                                         note="Final receipt records 260 chairs")
    assert replay["replayed"] is True
    assert replay["event"]["event_id"] == delivery["event"]["event_id"]
    assert replay["request_id"] == "request-retry"
    assert len(restarted.get_events(order_ref)) == 2
    with pytest.raises(ValueError, match="already final"):
        restarted.record_delivery(order_ref, 300, "another-delivery", "another-request")


def test_price_change_blocks_completion_until_new_decision_is_approved():
    merchant = ReferenceMerchant()
    approved = action(merchant)
    session = merchant.create_session(approved, "create", "request-create")
    item = next(x for x in merchant.get_catalog() if x["supplier_id"] == "supplier-b")
    merchant.set_catalog_item({**item, "unit_price_minor": 610000})
    blocked = merchant.complete_session(session["id"], approved, "complete-old", "request-old")
    assert blocked["status"] == "not_ready_for_payment"
    assert blocked["requires_approval"] is True
    assert blocked["external_order_ref"] is None
    assert blocked["terms"]["total_minor"] == 183000000
    assert "order" not in blocked
    revised = action(merchant, version=2)
    updated = merchant.update_session(session["id"], revised, "update", "request-update")
    assert updated["status"] == "ready_for_payment"
    complete = merchant.complete_session(session["id"], revised, "complete-new", "request-new")
    assert complete["order"]["decision_version"] == 2
    assert complete["order"]["approved_terms"]["total_minor"] == 183000000


def test_price_even_lower_requires_exact_renewed_approval():
    merchant = ReferenceMerchant()
    approved = action(merchant)
    session = merchant.create_session(approved, "create", "req")
    item = next(x for x in merchant.get_catalog() if x["supplier_id"] == "supplier-b")
    merchant.set_catalog_item({**item, "unit_price_minor": 580000})
    assert merchant.get_session(session["id"])["requires_approval"] is True
    result = merchant.complete_session(session["id"], approved, "complete", "req")
    assert result["external_order_ref"] is None


def test_budget_or_delivery_changes_never_create_order():
    for changed in ({"unit_price_minor": 700000}, {"delivery_days": 31}):
        merchant = ReferenceMerchant()
        approved = action(merchant)
        session = merchant.create_session(approved, "create", "req")
        item = next(x for x in merchant.get_catalog() if x["supplier_id"] == "supplier-b")
        merchant.set_catalog_item({**item, **changed})
        result = merchant.complete_session(session["id"], approved, "complete", "req")
        assert result["status"] == "not_ready_for_payment"
        assert result["external_order_ref"] is None
        with pytest.raises(ValueError, match="policy"):
            merchant.update_session(session["id"], action(merchant, 2), "update", "req")


def test_idempotency_conflict_and_different_key_cannot_duplicate_action():
    merchant = ReferenceMerchant()
    approved = action(merchant)
    first = merchant.create_session(approved, "create", "req")
    second = merchant.create_session(approved, "another-key", "req2")
    assert second["id"] == first["id"]
    with pytest.raises(IdempotencyConflict):
        merchant.create_session(action(merchant, 2), "create", "req3")
    first_order = merchant.complete_session(first["id"], approved, "complete", "req4")
    second_order = merchant.complete_session(first["id"], approved, "another-complete", "req5")
    assert second_order["external_order_ref"] == first_order["external_order_ref"]
    assert len(merchant.get_events(first_order["external_order_ref"])) == 1


def test_cancel_and_invalid_transition_preserve_no_order():
    merchant = ReferenceMerchant()
    approved = action(merchant)
    session = merchant.create_session(approved, "create", "req")
    assert merchant.cancel_session(session["id"], "cancel", "req")["status"] == "canceled"
    assert merchant.cancel_session(session["id"], "cancel", "retry")["replayed"] is True
    with pytest.raises(ValueError, match="canceled"):
        merchant.complete_session(session["id"], approved, "complete", "req")
    with pytest.raises(ValueError, match="canceled"):
        merchant.update_session(session["id"], action(merchant, 2), "update", "req")


def test_mutated_approval_and_older_version_are_rejected():
    merchant = ReferenceMerchant()
    approved = action(merchant)
    session = merchant.create_session(approved, "create", "req")
    forged = deepcopy(approved)
    forged["terms"]["quantity"] = 260
    with pytest.raises(ValueError):
        merchant.complete_session(session["id"], forged, "bad", "req")
    wrong_decision = {**approved, "decision_hash": "a" * 64}
    with pytest.raises(ValueError, match="exact approved"):
        merchant.complete_session(session["id"], wrong_decision, "bad2", "req")
    with pytest.raises(ValueError, match="immutable decision version"):
        merchant.update_session(session["id"], wrong_decision, "bad3", "req")
    merchant.update_session(session["id"], action(merchant, 2), "update", "req")
    with pytest.raises(ValueError, match="older decision"):
        merchant.update_session(session["id"], approved, "downgrade", "req")


def test_reference_merchant_never_accepts_live_or_unlabelled_authorization():
    merchant = ReferenceMerchant()
    for overrides in ({"mode": "live"}, {"mode": None}, {"money_moved": True}, {"money_moved": 0}):
        with pytest.raises(ValueError, match="explicitly simulated"):
            merchant.create_session(action(merchant, **overrides), "create", "req")


@pytest.mark.parametrize("bad", [True, 1.0, "300", None, -1, 0, 10001])
def test_quantities_require_bounded_integers(bad):
    merchant = ReferenceMerchant()
    with pytest.raises(ValueError, match="quantity"):
        merchant.quote("supplier-b", "chair-b", bad, 200000000, 30)


def test_deliveries_use_cumulative_counts_and_terminal_final_receipt():
    merchant = ReferenceMerchant()
    order_ref = completed(merchant)["external_order_ref"]
    partial = merchant.record_delivery(order_ref, 100, "partial", "req", final=False)
    assert partial["discrepancy"] is False
    with pytest.raises(ValueError, match="Cumulative"):
        merchant.record_delivery(order_ref, 99, "backwards", "req", final=False)
    with pytest.raises(ValueError, match="Cumulative"):
        merchant.record_delivery(order_ref, 301, "extra", "req")
    final = merchant.record_delivery(order_ref, 300, "final", "req")
    assert final["order"]["status"] == "DELIVERED"
    assert final["discrepancy"] is False


def test_concurrent_retries_create_one_order_and_event(tmp_path):
    path = tmp_path / "shared.sqlite3"
    first = ReferenceMerchant(path)
    second = ReferenceMerchant(path)
    approved = action(first)
    session_id = first.create_session(approved, "create", "req")["id"]

    def retry(index):
        merchant = first if index % 2 else second
        return merchant.complete_session(session_id, approved, "same-key", f"req-{index}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(retry, range(16)))
    assert len({item["external_order_ref"] for item in results}) == 1
    assert sum(not item["replayed"] for item in results) == 1
    assert len(first.get_events(results[0]["external_order_ref"])) == 1
