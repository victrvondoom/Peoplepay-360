import pytest

from beacon.peoplepay.transaction import Transaction
from gateway.commerce import create_dispute, sandbox_checkout, save_cart, update_delivery
from transaction.sqlite_store import SqliteTransactionStore


def cart(price=10000):
    return {"currency": "INR", "shipping_minor": 100, "tax_minor": 50,
            "items": [{"title": "Desk", "merchant": "Test store", "variant": "Oak",
                       "quantity": 2, "unit_price_minor": price}]}


def transaction():
    return Transaction.create(user_id="owner", raw_utterance="Desk under INR 1000")


def test_sandbox_order_persistence_and_replay(tmp_path):
    txn = transaction()
    saved = save_cart(txn, cart(), "owner")
    assert saved["total"]["minor"] == 20150
    confirmation = {"confirm_sandbox": True, "cart_hash": saved["cart_hash"]}
    first = sandbox_checkout(txn, confirmation, "owner")
    assert not first["order"]["money_moved"]
    create_dispute(txn, {"issue": "Wrong item", "remedy": "Replacement"}, "owner")
    update_delivery(txn, {"status": "SHIPPED", "note": "Manual update"}, "owner")
    assert txn.context["fulfillment"]["dispute"]["submitted"] is False
    with SqliteTransactionStore(tmp_path / "orders.db") as store:
        store.put(txn)
    with SqliteTransactionStore(tmp_path / "orders.db") as store:
        restored = store.get(txn.transaction_id)
        replay = sandbox_checkout(restored, confirmation, "owner")
        assert replay["replayed"]
        assert replay["order"]["order_id"] == first["order"]["order_id"]
        assert restored.ledger.verify_chain()[0]
        with pytest.raises(ValueError, match="already has an order"):
            save_cart(restored, cart(), "owner")


def test_budget_checked_without_plan():
    txn = transaction()
    saved = save_cart(txn, cart(60000), "owner")
    with pytest.raises(ValueError, match="budget"):
        sandbox_checkout(txn, {"confirm_sandbox": True, "cart_hash": saved["cart_hash"]}, "owner")


def test_confirmation_and_changed_cart():
    txn = transaction()
    saved = save_cart(txn, cart(), "owner")
    with pytest.raises(ValueError, match="confirmation"):
        sandbox_checkout(txn, {"cart_hash": saved["cart_hash"]}, "owner")
    save_cart(txn, cart(11000), "owner")
    with pytest.raises(ValueError, match="changed"):
        sandbox_checkout(txn, {"confirm_sandbox": True, "cart_hash": saved["cart_hash"]}, "owner")


@pytest.mark.parametrize("value", [-1, True, 1.2, "100", None])
def test_invalid_price(value):
    with pytest.raises(ValueError):
        save_cart(transaction(), cart(value), "owner")


def test_invalid_delivery_transition():
    txn = transaction()
    saved = save_cart(txn, cart(), "owner")
    sandbox_checkout(txn, {"confirm_sandbox": True, "cart_hash": saved["cart_hash"]}, "owner")
    with pytest.raises(ValueError, match="Cannot change"):
        update_delivery(txn, {"status": "DELIVERED", "note": "Skip shipping"}, "owner")
