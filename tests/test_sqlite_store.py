"""Tests for the durable, event-sourced SQLite store.

The claim this store makes is narrow and strong: **a stored transaction's
history cannot be quietly edited and still load.**  So the tests that matter most
are the tampering ones -- editing a row, deleting a row, and rewriting a detail
must each be caught on load rather than believed.

The rest guard against the quieter failure: silently *losing* an authorization
constraint across a restart.  A dropped ``blocked_merchants`` or a dropped budget
cap would widen what the agent may do, which is the worst direction to fail in,
so every mandate field is round-tripped explicitly.
"""

from __future__ import annotations

import sqlite3

import pytest

from beacon.assurance import AutonomyLevel, IntentMandate, Money, State
from beacon.peoplepay import (
    ConditionalGrant,
    Permission,
    Transaction,
    TransactionType,
)
from transaction.sqlite_store import (
    SCHEMA_VERSION,
    LedgerIntegrityError,
    SqliteTransactionStore,
)
from transaction.store import TransactionNotFound, TransactionStore

TAMIL = "எனக்கு ₹50,000 குள்ள ஒரு நல்ல laptop தேவை."


@pytest.fixture()
def db(tmp_path):
    """A fresh store per test, closed afterwards."""
    store = SqliteTransactionStore(tmp_path / "txn.db")
    yield store
    store.close()


def _seeded(user_id: str = "user-a", *, budget: str | None = "50000") -> Transaction:
    tx = Transaction.create(user_id=user_id, raw_utterance=TAMIL, language="ta-Latn")
    tx.capture_intent(
        IntentMandate.create(
            user_id=user_id,
            raw_utterance=TAMIL,
            product_query="laptop",
            max_amount=Money.of(budget, "INR") if budget else None,
        ),
        normalized_intent="laptop",
    )
    return tx


class TestProtocolConformance:
    def test_it_satisfies_the_transaction_store_protocol(self, db):
        """A drop-in for the in-memory store, so the gateway needs no change."""
        assert isinstance(db, TransactionStore)

    def test_a_fresh_file_records_its_schema_version(self, db):
        assert db.stats()["schema_version"] == SCHEMA_VERSION

    def test_a_file_from_a_future_schema_is_refused(self, tmp_path):
        """Misreading stored money is worse than refusing to open the file."""
        path = tmp_path / "future.db"
        SqliteTransactionStore(path).close()
        conn = sqlite3.connect(str(path))
        conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
        conn.commit()
        conn.close()
        with pytest.raises(RuntimeError, match="schema version 999"):
            SqliteTransactionStore(path)


class TestDurability:
    """The whole point: state survives the process ending."""

    def test_a_transaction_survives_a_restart(self, tmp_path):
        path = tmp_path / "txn.db"
        first = SqliteTransactionStore(path)
        tx = _seeded()
        first.put(tx)
        first.close()

        second = SqliteTransactionStore(path)
        back = second.get(tx.transaction_id)
        assert back.transaction_id == tx.transaction_id
        assert back.state is State.INTENT_CAPTURED
        second.close()

    def test_the_raw_utterance_survives_byte_for_byte(self, tmp_path):
        """Invariant 2 has to hold across storage, not just in memory."""
        path = tmp_path / "txn.db"
        store = SqliteTransactionStore(path)
        tx = _seeded()
        store.put(tx)
        store.close()
        reopened = SqliteTransactionStore(path)
        assert reopened.get(tx.transaction_id).raw_utterance == TAMIL
        reopened.close()

    def test_the_budget_cap_survives(self, db):
        """Losing this would widen what the agent may spend after a restart."""
        tx = _seeded(budget="50000")
        db.put(tx)
        back = db.get(tx.transaction_id)
        assert back.mandate is not None
        assert back.mandate.max_amount == Money.of("50000", "INR")
        assert back.mandate.max_amount.minor == 5000000

    def test_every_mandate_constraint_survives(self, db):
        """A dropped constraint widens authority; check the restrictive ones."""
        tx = Transaction.create(user_id="user-a", raw_utterance=TAMIL)
        tx.capture_intent(
            IntentMandate.create(
                user_id="user-a",
                raw_utterance=TAMIL,
                product_query="laptop",
                max_amount=Money.of("50000", "INR"),
                required_condition="new",
                blocked_merchants=("dodgy-shop", "other-shop"),
                allowed_merchants=("good-shop",),
                allowed_categories=("electronics",),
                require_warranty=True,
                require_return_policy=True,
                max_delivery_days=2,
                quantity=3,
                interpreted_by="model/x",
            ),
            normalized_intent="laptop",
        )
        db.put(tx)
        m = db.get(tx.transaction_id).mandate
        assert m is not None
        assert m.required_condition == "new"
        assert m.blocked_merchants == ("dodgy-shop", "other-shop")
        assert m.allowed_merchants == ("good-shop",)
        assert m.allowed_categories == ("electronics",)
        assert m.require_warranty is True
        assert m.require_return_policy is True
        assert m.max_delivery_days == 2
        assert m.quantity == 3
        assert m.interpreted_by == "model/x"

    def test_a_transaction_with_no_mandate_round_trips(self, db):
        tx = Transaction.create(user_id="user-a", raw_utterance=TAMIL)
        db.put(tx)
        assert db.get(tx.transaction_id).mandate is None

    def test_permissions_survive_and_payment_stays_denied(self, db):
        """Invariant 6 must not be relaxed by a round trip."""
        tx = _seeded()
        db.put(tx)
        back = db.get(tx.transaction_id)
        assert back.permissions.allows(Permission.DISCOVERY) is True
        assert back.permissions.allows(Permission.PAYMENT) is False

    def test_a_conditional_grant_keeps_its_cap_after_a_restart(self, tmp_path):
        """The cap is the authorization; an unbounded reload would be a breach."""
        path = tmp_path / "txn.db"
        store = SqliteTransactionStore(path)
        tx = _seeded()
        tx.grant_conditional(
            ConditionalGrant(
                permission=Permission.PAYMENT,
                max_amount=Money.of("45000", "INR"),
                raw_utterance="45k varaikkum",
            ),
            actor="test",
        )
        store.put(tx)
        store.close()

        reopened = SqliteTransactionStore(path)
        back = reopened.get(tx.transaction_id)
        assert back.permissions.allows(
            Permission.PAYMENT, amount=Money.of("44000", "INR")
        )
        assert not back.permissions.allows(
            Permission.PAYMENT, amount=Money.of("47000", "INR")
        )
        assert back.permissions.conditional[0].raw_utterance == "45k varaikkum"
        reopened.close()

    def test_autonomy_level_survives(self, db):
        tx = _seeded()
        tx.permissions = tx.permissions.with_autonomy(AutonomyLevel.CONDITIONAL)
        db.put(tx)
        assert db.get(tx.transaction_id).permissions.autonomy is (
            AutonomyLevel.CONDITIONAL
        )

    def test_context_and_plan_survive(self, db):
        tx = _seeded()
        tx.attach_context("market", {"median": 4599900}, actor="test")
        tx.plan = {"summary": "shortlist", "executed": False}
        db.put(tx)
        back = db.get(tx.transaction_id)
        assert back.context["market"]["median"] == 4599900
        assert back.plan == {"summary": "shortlist", "executed": False}

    def test_transaction_type_survives(self, db):
        tx = Transaction.create(
            user_id="user-a",
            raw_utterance=TAMIL,
            transaction_type=TransactionType.TRANSPORT,
        )
        db.put(tx)
        assert db.get(tx.transaction_id).transaction_type is TransactionType.TRANSPORT


class TestLedgerReplay:
    """Events are the source of truth, and they are re-verified on load."""

    def test_every_event_is_stored_and_replayed(self, db):
        tx = _seeded()
        expected = len(tx.ledger)
        db.put(tx)
        assert len(db.get(tx.transaction_id).ledger) == expected

    def test_the_chain_verifies_after_a_round_trip(self, db):
        tx = _seeded()
        db.put(tx)
        ok, _ = db.get(tx.transaction_id).ledger.verify_chain()
        assert ok is True

    def test_putting_twice_does_not_duplicate_events(self, db):
        """Events are append-only; a re-put must not rewrite history."""
        tx = _seeded()
        db.put(tx)
        db.put(tx)
        assert len(db.get(tx.transaction_id).ledger) == len(tx.ledger)
        assert db.stats()["ledger_events"] == len(tx.ledger)

    def test_new_events_are_appended_on_a_later_put(self, db):
        tx = _seeded()
        db.put(tx)
        before = len(tx.ledger)
        tx.transition_to(State.DISCOVERING, actor="test")
        db.put(tx)
        back = db.get(tx.transaction_id)
        assert len(back.ledger) == before + 1
        assert back.state is State.DISCOVERING

    def test_event_actors_and_details_survive(self, db):
        tx = _seeded()
        db.put(tx)
        replayed = db.get(tx.transaction_id).ledger.events
        assert all(e.actor.strip() for e in replayed)
        assert any(e.detail for e in replayed)


class TestTamperDetection:
    """The reason to store events rather than a state row."""

    def test_editing_an_event_is_detected_on_load(self, tmp_path):
        path = tmp_path / "txn.db"
        store = SqliteTransactionStore(path)
        tx = _seeded()
        store.put(tx)
        store.close()

        conn = sqlite3.connect(str(path))
        conn.execute(
            "UPDATE ledger_events SET actor = 'somebody-else' "
            "WHERE transaction_id = ? AND seq = 1",
            (tx.transaction_id,),
        )
        conn.commit()
        conn.close()

        reopened = SqliteTransactionStore(path)
        with pytest.raises(LedgerIntegrityError, match="tampered content at seq=1"):
            reopened.get(tx.transaction_id)
        reopened.close()

    def test_deleting_an_event_is_detected_on_load(self, tmp_path):
        """Truncating history must not look like a shorter, valid history."""
        path = tmp_path / "txn.db"
        store = SqliteTransactionStore(path)
        tx = _seeded()
        store.put(tx)
        store.close()

        conn = sqlite3.connect(str(path))
        conn.execute(
            "DELETE FROM ledger_events WHERE transaction_id = ? AND seq = 1",
            (tx.transaction_id,),
        )
        conn.commit()
        conn.close()

        reopened = SqliteTransactionStore(path)
        with pytest.raises(LedgerIntegrityError):
            reopened.get(tx.transaction_id)
        reopened.close()

    def test_rewriting_a_detail_field_is_detected(self, tmp_path):
        """The hash covers the detail, so changing an amount is caught."""
        path = tmp_path / "txn.db"
        store = SqliteTransactionStore(path)
        tx = _seeded()
        store.put(tx)
        store.close()

        conn = sqlite3.connect(str(path))
        conn.execute(
            'UPDATE ledger_events SET detail_json = \'{"tampered": true}\' '
            "WHERE transaction_id = ? AND seq = 2",
            (tx.transaction_id,),
        )
        conn.commit()
        conn.close()

        reopened = SqliteTransactionStore(path)
        with pytest.raises(LedgerIntegrityError):
            reopened.get(tx.transaction_id)
        reopened.close()

    def test_verify_all_names_the_broken_transaction(self, tmp_path):
        path = tmp_path / "txn.db"
        store = SqliteTransactionStore(path)
        good = _seeded("user-a")
        bad = _seeded("user-b")
        store.put(good)
        store.put(bad)
        store.close()

        conn = sqlite3.connect(str(path))
        conn.execute(
            "UPDATE ledger_events SET actor = 'x' WHERE transaction_id = ? AND seq = 1",
            (bad.transaction_id,),
        )
        conn.commit()
        conn.close()

        reopened = SqliteTransactionStore(path)
        broken = reopened.verify_all()
        assert bad.transaction_id in broken
        assert good.transaction_id not in broken
        reopened.close()

    def test_a_tampered_ledger_is_not_reported_as_missing(self, tmp_path):
        """Different failures need different excepts; this must not be a KeyError."""
        path = tmp_path / "txn.db"
        store = SqliteTransactionStore(path)
        tx = _seeded()
        store.put(tx)
        store.close()

        conn = sqlite3.connect(str(path))
        conn.execute(
            "UPDATE ledger_events SET actor = 'x' WHERE transaction_id = ? AND seq = 1",
            (tx.transaction_id,),
        )
        conn.commit()
        conn.close()

        reopened = SqliteTransactionStore(path)
        with pytest.raises(LedgerIntegrityError):
            reopened.get(tx.transaction_id)
        assert not issubclass(LedgerIntegrityError, TransactionNotFound)
        reopened.close()


class TestQueries:
    def test_get_missing_raises_transaction_not_found(self, db):
        with pytest.raises(TransactionNotFound):
            db.get("txn-nope")

    def test_exists_does_not_raise(self, db):
        assert db.exists("txn-nope") is False

    def test_for_user_isolates_users(self, db):
        mine, theirs = _seeded("user-a"), _seeded("user-b")
        db.put(mine)
        db.put(theirs)
        assert [t.transaction_id for t in db.for_user("user-a")] == [
            mine.transaction_id
        ]
        assert db.for_user("user-c") == ()

    def test_open_transactions_excludes_terminal_ones(self, db):
        live = _seeded("user-a")
        done = _seeded("user-b")
        done.transition_to(State.CANCELLED, actor="test")
        db.put(live)
        db.put(done)
        open_ids = {t.transaction_id for t in db.open_transactions()}
        assert live.transaction_id in open_ids
        assert done.transaction_id not in open_ids

    def test_in_state_filters_exactly(self, db):
        tx = _seeded()
        db.put(tx)
        assert [t.transaction_id for t in db.in_state(State.INTENT_CAPTURED)] == [
            tx.transaction_id
        ]
        assert db.in_state(State.SETTLED) == ()

    def test_len_counts_transactions_not_events(self, db):
        db.put(_seeded("user-a"))
        db.put(_seeded("user-b"))
        assert len(db) == 2
        assert db.stats()["ledger_events"] > 2

    def test_stats_reports_without_loading_aggregates(self, db):
        db.put(_seeded())
        stats = db.stats()
        assert stats["transactions"] == 1
        assert "checked_at" in stats


class TestNoFloats:
    """`Money` refuses floats; storage must not reintroduce them."""

    def test_stored_money_is_minor_units_in_the_raw_row(self, db):
        tx = _seeded(budget="50000")
        db.put(tx)
        row = db._conn.execute(  # noqa: SLF001 - inspecting the row is the point
            "SELECT mandate_json FROM transactions WHERE transaction_id = ?",
            (tx.transaction_id,),
        ).fetchone()
        assert '"minor": 5000000' in row["mandate_json"]
        assert "50000.0" not in row["mandate_json"]

    def test_a_restored_amount_is_exactly_equal_not_approximately(self, db):
        tx = _seeded(budget="19999.99")
        db.put(tx)
        restored = db.get(tx.transaction_id).mandate
        assert restored is not None
        assert restored.max_amount == Money.of("19999.99", "INR")
