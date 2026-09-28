"""The ten critical invariants of §30, one test class each.

These are the tests that are supposed to fail loudly if someone later "fixes"
a refusal into a convenience.  Each class names the invariant it pins so that a
failure report says which promise broke, not just which function did.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from beacon.assurance import (
    AutonomyLevel,
    EvidenceClass,
    IllegalTransition,
    IntentMandate,
    Money,
    State,
    utcnow,
)
from beacon.peoplepay import (
    AuthorityError,
    ConditionalGrant,
    MemoryScope,
    MemoryVault,
    PeoplePayAgent,
    PeoplePayNodeKind,
    Permission,
    PermissionSet,
    PromotionError,
    ResponseKind,
    Retention,
    SourceType,
    ToolRegistry,
    Transaction,
    TransactionOwnershipError,
    TransactionType,
    Visibility,
    VisibilityError,
)

TAMIL = "எனக்கு ₹50,000 குள்ள ஒரு நல்ல laptop தேவை."
TANGLISH = "₹45,000 குள்ள irundha vaangalam."


def _txn(**kw):
    kw.setdefault("user_id", "user-rupesh")
    kw.setdefault("raw_utterance", TAMIL)
    return Transaction.create(**kw)


# --- 1 -------------------------------------------------------------------


class TestInvariant1OneCanonicalId:
    """One transaction has exactly one canonical transaction_id."""

    def test_id_is_stable_across_mutation(self):
        txn = _txn()
        original = txn.transaction_id
        txn.transition_to(State.INTENT_CAPTURED, actor="t")
        txn.attach_context("market", {"k": 1}, actor="t")
        assert txn.transaction_id == original

    def test_graph_and_ledger_share_the_id(self):
        txn = _txn()
        assert txn.graph.transaction_id == txn.transaction_id
        assert txn.ledger.transaction_id == txn.transaction_id

    def test_two_transactions_never_share_an_id(self):
        assert _txn().transaction_id != _txn().transaction_id

    def test_serialization_reports_the_same_id(self):
        txn = _txn()
        assert txn.to_dict()["transaction_id"] == txn.transaction_id


# --- 2 -------------------------------------------------------------------


class TestInvariant2RawUtteranceNeverOverwritten:
    """Raw user utterance is never overwritten."""

    def test_tamil_is_preserved_byte_for_byte(self):
        assert _txn(raw_utterance=TAMIL).raw_utterance == TAMIL

    def test_normalized_intent_sits_beside_it_not_over_it(self):
        txn = _txn()
        mandate = IntentMandate.create(
            user_id=txn.user_id, raw_utterance=TAMIL, product_query="laptop"
        )
        txn.capture_intent(mandate, normalized_intent="laptop")
        assert txn.raw_utterance == TAMIL
        assert txn.normalized_intent == "laptop"

    def test_mandate_built_from_a_translation_is_refused(self):
        """A translation must not be able to become the consent record."""
        txn = _txn(raw_utterance=TAMIL)
        translated = IntentMandate.create(
            user_id=txn.user_id,
            raw_utterance="I need a good laptop under 50,000",
            product_query="laptop",
        )
        with pytest.raises(ValueError, match="consent record cannot be substituted"):
            txn.capture_intent(translated, normalized_intent="laptop")

    def test_empty_utterance_is_refused(self):
        with pytest.raises(ValueError, match="raw_utterance is required"):
            Transaction.create(user_id="u", raw_utterance="   ")


# --- 3 -------------------------------------------------------------------


class TestInvariant3InferenceIsNotPreference:
    """Inference cannot silently become preference."""

    def test_they_are_different_node_kinds(self):
        assert (
            PeoplePayNodeKind.USER_PREFERENCE is not PeoplePayNodeKind.USER_INFERENCE
        )

    def test_promotion_without_confirmation_is_refused(self):
        vault = MemoryVault("u")
        inf = vault.infer(key="brand", value="Sony", confidence=0.8)
        with pytest.raises(PromotionError, match="explicit confirmation"):
            vault.promote_inference(inf.item_id, confirmed_by_user=False)

    def test_promotion_creates_a_new_item_and_leaves_the_original(self):
        vault = MemoryVault("u")
        inf = vault.infer(key="brand", value="Sony", confidence=0.8)
        pref = vault.promote_inference(inf.item_id, confirmed_by_user=True)
        assert pref.item_id != inf.item_id
        assert pref.derived_from == inf.item_id
        assert vault.get(inf.item_id).kind is PeoplePayNodeKind.USER_INFERENCE
        assert pref.kind is PeoplePayNodeKind.USER_PREFERENCE

    def test_a_preference_may_not_carry_a_confidence_score(self):
        vault = MemoryVault("u")
        with pytest.raises(ValueError, match="must not carry a confidence"):
            vault.remember(
                kind=PeoplePayNodeKind.USER_PREFERENCE,
                key="brand",
                value="Sony",
                source=SourceType.SELF_REPORTED,
                confidence=0.9,
            )

    def test_an_inference_must_carry_a_confidence_score(self):
        vault = MemoryVault("u")
        with pytest.raises(ValueError, match="must carry a confidence"):
            vault.remember(
                kind=PeoplePayNodeKind.USER_INFERENCE,
                key="brand",
                value="Sony",
                source=SourceType.SYSTEM_DERIVED,
            )

    def test_only_an_inference_can_be_promoted(self):
        vault = MemoryVault("u")
        fact = vault.remember(
            kind=PeoplePayNodeKind.USER_FACT,
            key="city",
            value="Chennai",
            source=SourceType.SELF_REPORTED,
        )
        with pytest.raises(PromotionError, match="only a USER_INFERENCE"):
            vault.promote_inference(fact.item_id, confirmed_by_user=True)

    def test_default_user_memory_read_withholds_inferences(self):
        vault = MemoryVault("u")
        vault.infer(key="brand", value="Sony", confidence=0.8)
        vault.state_preference(key="city", value="Chennai")
        assert all(
            i.kind is not PeoplePayNodeKind.USER_INFERENCE
            for i in vault.get_user_memory()
        )
        assert len(vault.get_user_memory(include_inferences=True)) == 2

    def test_prompt_rendering_withholds_inferences(self):
        vault = MemoryVault("u")
        vault.infer(key="brand", value="Sony", confidence=0.8)
        rendered = vault.format_for_prompt()
        assert "Sony" not in rendered
        assert "withheld" in rendered


# --- 4 -------------------------------------------------------------------


class TestInvariant4SandboxNeverBecomesProduction:
    """Sandbox results cannot become production evidence."""

    def test_sandbox_provenance_downgrades_a_verified_claim(self):
        txn = _txn()
        obs = txn.observation(
            field_name="price",
            value=4999900,
            source="sandbox.catalog",
            source_type=SourceType.SANDBOX,
            evidence_class=EvidenceClass.VERIFIED,
            sandbox=True,
        )
        assert obs.evidence_class is EvidenceClass.SANDBOX

    def test_graph_reports_sandbox_contamination(self):
        txn = _txn()
        assert not txn.has_sandbox_evidence
        txn.add_evidence(
            PeoplePayNodeKind.PRICE_OBSERVATION,
            actor="t",
            source="sandbox.catalog",
            source_type=SourceType.SANDBOX,
            observations=(
                txn.observation(
                    field_name="price",
                    value=1,
                    source="sandbox.catalog",
                    source_type=SourceType.SANDBOX,
                    sandbox=True,
                ),
            ),
        )
        assert txn.has_sandbox_evidence

    def test_a_plan_on_sandbox_evidence_is_never_valid(self):
        tools = ToolRegistry()
        txn = tools.create_transaction(user_id="u", raw_utterance=TAMIL)
        mandate = IntentMandate.create(
            user_id="u", raw_utterance=TAMIL, product_query="laptop"
        )
        txn.capture_intent(mandate, normalized_intent="laptop")
        tools.add_evidence(
            txn.transaction_id,
            user_id="u",
            kind=PeoplePayNodeKind.PRICE_OBSERVATION,
            source="sandbox.catalog",
            source_type=SourceType.SANDBOX,
            sandbox=True,
        )
        tools.create_plan(txn.transaction_id, user_id="u", summary="buy", steps=("a",))
        result = tools.validate_plan(txn.transaction_id, user_id="u")
        assert result["valid"] is False
        assert any("sandbox" in p for p in result["problems"])

    def test_sandbox_source_type_is_not_decision_capable(self):
        from beacon.peoplepay import DECISION_CAPABLE_SOURCES

        assert SourceType.SANDBOX not in DECISION_CAPABLE_SOURCES


# --- 5 -------------------------------------------------------------------


class TestInvariant5PrivateStaysPrivate:
    """Private memory cannot become shared memory without explicit permission."""

    def test_everything_is_private_by_default(self):
        vault = MemoryVault("u")
        item = vault.state_preference(key="brand", value="Sony")
        assert item.visibility is Visibility.PRIVATE

    def test_nothing_is_shareable_by_default(self):
        vault = MemoryVault("u")
        vault.state_preference(key="brand", value="Sony")
        assert vault.shareable(Visibility.SHARED_WITH_COMMUNITY) == []

    def test_sharing_requires_a_consent_reference(self):
        vault = MemoryVault("u")
        item = vault.state_preference(key="brand", value="Sony")
        with pytest.raises(VisibilityError, match="consent reference"):
            vault.share(
                item.item_id,
                visibility=Visibility.SHARED_WITH_COMMUNITY,
                consent_reference="  ",
            )

    def test_sharing_with_consent_records_why(self):
        vault = MemoryVault("u")
        item = vault.state_preference(key="brand", value="Sony")
        shared = vault.share(
            item.item_id,
            visibility=Visibility.SHARED_WITH_COMMUNITY,
            consent_reference="consent-2026-09-27",
        )
        assert shared.visibility is Visibility.SHARED_WITH_COMMUNITY
        assert shared.note == "consent-2026-09-27"
        assert shared.item_id == item.item_id

    def test_a_shared_personal_item_must_carry_a_reason(self):
        from beacon.peoplepay import MemoryItem

        with pytest.raises(ValueError, match="must record why"):
            MemoryItem(
                item_id="m1",
                user_id="u",
                kind=PeoplePayNodeKind.USER_PREFERENCE,
                key="brand",
                value="Sony",
                source=SourceType.SELF_REPORTED,
                visibility=Visibility.PUBLIC,
            )


# --- 6 and 7 -------------------------------------------------------------


class TestInvariant6And7AuthorityIsNotTransitive:
    """Search permission does not imply payment; planning does not imply execution."""

    def test_a_fresh_transaction_can_search_but_not_pay(self):
        txn = _txn()
        assert txn.permissions.allows(Permission.DISCOVERY)
        assert txn.permissions.allows(Permission.PLANNING)
        assert not txn.permissions.allows(Permission.PAYMENT)
        assert not txn.permissions.allows(Permission.BOOKING)
        assert not txn.permissions.allows(Permission.SHARING)

    def test_granting_discovery_does_not_grant_payment(self):
        perms = PermissionSet().grant(Permission.DISCOVERY)
        assert perms.allows(Permission.DISCOVERY)
        assert not perms.allows(Permission.PAYMENT)

    def test_granting_planning_does_not_grant_booking(self):
        perms = PermissionSet().grant(Permission.PLANNING)
        assert not perms.allows(Permission.BOOKING)

    def test_requiring_a_missing_permission_raises(self):
        txn = _txn()
        with pytest.raises(AuthorityError, match="PAYMENT"):
            txn.require_permission(Permission.PAYMENT)

    def test_a_denied_permission_is_logged(self):
        txn = _txn()
        before = len(txn.ledger)
        with pytest.raises(AuthorityError):
            txn.require_permission(Permission.PAYMENT)
        assert len(txn.ledger) == before + 1
        assert txn.ledger.events[-1].detail["outcome"] == "DENIED"

    def test_find_me_a_laptop_does_not_authorize_buying_it(self):
        agent = PeoplePayAgent()
        txn, _ = agent.handle_intent(
            user_id="u", utterance=TAMIL, product_query="laptop"
        )
        reply = agent.attempt_payment(
            txn.transaction_id, user_id="u", amount=Money.of("49999", "INR")
        )
        assert reply.kind is ResponseKind.AUTHORIZATION_REQUEST
        assert Permission.PAYMENT in reply.permissions_required

    def test_revoking_removes_conditional_grants_too(self):
        perms = PermissionSet().grant_conditional(
            ConditionalGrant(
                permission=Permission.PAYMENT, max_amount=Money.of("100", "INR")
            )
        )
        assert perms.allows(Permission.PAYMENT, amount=Money.of("50", "INR"))
        assert not perms.revoke(Permission.PAYMENT).allows(
            Permission.PAYMENT, amount=Money.of("50", "INR")
        )


# --- 8 -------------------------------------------------------------------


class TestInvariant8PaymentAuthorizationIsExplicit:
    """Payment authorization must be explicit or conditionally authorized."""

    def test_a_conditional_grant_covers_an_amount_under_the_cap(self):
        grant = ConditionalGrant(
            permission=Permission.PAYMENT, max_amount=Money.of("45000", "INR")
        )
        assert grant.covers(Money.of("44999", "INR"))
        assert grant.covers(Money.of("45000", "INR"))

    def test_a_conditional_grant_refuses_an_amount_over_the_cap(self):
        grant = ConditionalGrant(
            permission=Permission.PAYMENT, max_amount=Money.of("45000", "INR")
        )
        assert not grant.covers(Money.of("45001", "INR"))

    def test_a_capped_grant_does_not_cover_an_unknown_amount(self):
        """"Buy if under 45,000" is not consent to buy at an unknown price."""
        grant = ConditionalGrant(
            permission=Permission.PAYMENT, max_amount=Money.of("45000", "INR")
        )
        assert not grant.covers(None)

    def test_a_grant_in_another_currency_does_not_cover(self):
        grant = ConditionalGrant(
            permission=Permission.PAYMENT, max_amount=Money.of("45000", "INR")
        )
        assert not grant.covers(Money.of("100", "USD"))

    def test_an_expired_grant_covers_nothing(self):
        grant = ConditionalGrant(
            permission=Permission.PAYMENT,
            max_amount=Money.of("45000", "INR"),
            expires_at=utcnow() - timedelta(seconds=1),
        )
        assert grant.is_expired()
        assert not grant.covers(Money.of("1", "INR"))

    def test_tanglish_conditional_authorization_is_recorded(self):
        agent = PeoplePayAgent()
        txn, _ = agent.handle_intent(
            user_id="u", utterance=TAMIL, product_query="laptop"
        )
        reply = agent.handle_conditional_authorization(
            txn.transaction_id, user_id="u", utterance=TANGLISH
        )
        assert reply.kind is ResponseKind.ACTION_RESULT
        assert txn.permissions.autonomy is AutonomyLevel.CONDITIONAL
        assert txn.permissions.allows(
            Permission.PAYMENT, amount=Money.of("44000", "INR")
        )
        assert not txn.permissions.allows(
            Permission.PAYMENT, amount=Money.of("46000", "INR")
        )

    def test_a_conditional_utterance_without_a_cap_asks_instead_of_granting(self):
        agent = PeoplePayAgent()
        txn, _ = agent.handle_intent(
            user_id="u", utterance=TAMIL, product_query="laptop"
        )
        reply = agent.handle_conditional_authorization(
            txn.transaction_id, user_id="u", utterance="vaangalam"
        )
        assert reply.kind is ResponseKind.QUESTION
        assert not txn.permissions.allows(
            Permission.PAYMENT, amount=Money.of("1", "INR")
        )

    def test_even_an_authorized_payment_does_not_execute_in_phase_4(self):
        """No payment provider exists, so success is never reported."""
        agent = PeoplePayAgent()
        txn, _ = agent.handle_intent(
            user_id="u", utterance=TAMIL, product_query="laptop"
        )
        agent.handle_conditional_authorization(
            txn.transaction_id, user_id="u", utterance=TANGLISH
        )
        reply = agent.attempt_payment(
            txn.transaction_id, user_id="u", amount=Money.of("44000", "INR")
        )
        assert reply.kind is ResponseKind.ACTION_REQUEST
        assert reply.detail["executed"] is False
        assert reply.detail["provider_status"] == "NOT_CONFIGURED"


# --- 9 -------------------------------------------------------------------


class TestInvariant9SmallCohortsAreNotExposed:
    """Small-cohort private purchase information must not be exposed.

    Phase 4 builds the data model, not the aggregation service (§17).  What is
    testable now is that the fields which would leak are private by default and
    separately consented -- so no aggregate can be built from them by accident.
    """

    def test_price_and_date_are_separate_items_from_the_experience(self):
        vault = MemoryVault("u")
        exp = vault.remember(
            kind=PeoplePayNodeKind.COMMUNITY_EVIDENCE,
            key="experience",
            value="battery lasts well",
            source=SourceType.VERIFIED_USER_EXPERIENCE,
        )
        price = vault.remember(
            kind=PeoplePayNodeKind.PRICE_OBSERVATION,
            key="purchase_price",
            value={"minor": 4999900, "currency": "INR"},
            source=SourceType.SELF_REPORTED,
        )
        assert exp.item_id != price.item_id
        assert exp.visibility is Visibility.PRIVATE
        assert price.visibility is Visibility.PRIVATE

    def test_sharing_an_experience_does_not_share_its_price(self):
        vault = MemoryVault("u")
        exp = vault.remember(
            kind=PeoplePayNodeKind.COMMUNITY_EVIDENCE,
            key="experience",
            value="good",
            source=SourceType.VERIFIED_USER_EXPERIENCE,
        )
        vault.remember(
            kind=PeoplePayNodeKind.PRICE_OBSERVATION,
            key="purchase_price",
            value={"minor": 4999900, "currency": "INR"},
            source=SourceType.SELF_REPORTED,
        )
        vault.share(
            exp.item_id,
            visibility=Visibility.SHARED_WITH_COMMUNITY,
            consent_reference="consent-1",
        )
        shared = vault.shareable(Visibility.SHARED_WITH_COMMUNITY)
        assert [i.key for i in shared] == ["experience"]

    def test_sharing_requires_the_sharing_permission_on_a_transaction(self):
        txn = _txn()
        assert not txn.permissions.allows(Permission.SHARING)


# --- 10 ------------------------------------------------------------------


class TestInvariant10EvidenceRetainsProvenance:
    """Every external evidence item retains provenance."""

    def test_an_observation_records_source_and_retrieval_time(self):
        txn = _txn()
        obs = txn.observation(
            field_name="price",
            value=4999900,
            source="example.merchant",
            source_type=SourceType.PRIMARY_SOURCE,
            source_url="https://example.test/p/1",
        )
        assert obs.provenance.source == "example.merchant"
        assert obs.provenance.source_url == "https://example.test/p/1"
        assert obs.provenance.retrieved_at is not None

    def test_source_type_is_stored_on_the_node(self):
        """A Google review and a YouTube video must not collapse together."""
        txn = _txn()
        node_id = txn.add_evidence(
            PeoplePayNodeKind.VIDEO_EVIDENCE,
            actor="t",
            source="youtube",
            source_type=SourceType.CREATOR_CONTENT,
        )
        node = txn.graph.get(node_id)
        assert node.payload["source_type"] == "CREATOR_CONTENT"
        assert node.payload["source"] == "youtube"

    def test_creator_content_is_not_decision_capable(self):
        from beacon.peoplepay import DECISION_CAPABLE_SOURCES

        assert SourceType.CREATOR_CONTENT not in DECISION_CAPABLE_SOURCES
        assert SourceType.COMMUNITY_DISCUSSION not in DECISION_CAPABLE_SOURCES
        assert SourceType.MARKETPLACE_LISTING not in DECISION_CAPABLE_SOURCES

    def test_a_missing_value_cannot_carry_a_number(self):
        txn = _txn()
        with pytest.raises(ValueError, match="must not be filled in"):
            txn.observation(
                field_name="price",
                value=4999900,
                source="nowhere",
                source_type=SourceType.PRIMARY_SOURCE,
                evidence_class=EvidenceClass.UNAVAILABLE,
            )

    def test_unknown_and_unavailable_and_conflicting_survive(self):
        """The existing EvidenceClass vocabulary is reused, not replaced."""
        txn = _txn()
        for klass in (EvidenceClass.UNKNOWN, EvidenceClass.UNAVAILABLE):
            obs = txn.observation(
                field_name="price",
                value=None,
                source="s",
                source_type=SourceType.PRIMARY_SOURCE,
                evidence_class=klass,
            )
            assert obs.evidence_class is klass
        conflicting = txn.observation(
            field_name="price",
            value=1,
            source="s",
            source_type=SourceType.PRIMARY_SOURCE,
            evidence_class=EvidenceClass.CONFLICTING,
        )
        assert conflicting.evidence_class is EvidenceClass.CONFLICTING

    def test_every_evidence_write_appends_a_ledger_event(self):
        txn = _txn()
        before = len(txn.ledger)
        txn.add_evidence(
            PeoplePayNodeKind.MERCHANT,
            actor="t",
            source="example",
            source_type=SourceType.PRIMARY_SOURCE,
        )
        assert len(txn.ledger) == before + 1


# --- ownership and lifecycle --------------------------------------------


class TestOwnershipAndLifecycle:
    """§26 ownership, and that the lifecycle table stays the authority."""

    def test_another_user_cannot_read_a_transaction(self):
        tools = ToolRegistry()
        txn = tools.create_transaction(user_id="user-rupesh", raw_utterance=TAMIL)
        with pytest.raises(TransactionOwnershipError):
            tools.get_transaction(txn.transaction_id, user_id="user-other")

    def test_another_user_cannot_add_evidence(self):
        tools = ToolRegistry()
        txn = tools.create_transaction(user_id="user-rupesh", raw_utterance=TAMIL)
        with pytest.raises(TransactionOwnershipError):
            tools.add_evidence(
                txn.transaction_id,
                user_id="user-other",
                kind=PeoplePayNodeKind.MERCHANT,
                source="x",
                source_type=SourceType.PRIMARY_SOURCE,
            )

    def test_history_only_returns_the_callers_own_transactions(self):
        tools = ToolRegistry()
        tools.create_transaction(user_id="a", raw_utterance="one")
        tools.create_transaction(user_id="b", raw_utterance="two")
        assert len(tools.get_transaction_history(user_id="a")) == 1

    def test_a_mandate_for_another_user_is_refused(self):
        txn = _txn(user_id="user-rupesh")
        other = IntentMandate.create(
            user_id="user-other", raw_utterance=TAMIL, product_query="laptop"
        )
        with pytest.raises(TransactionOwnershipError):
            txn.capture_intent(other, normalized_intent="laptop")

    def test_an_illegal_transition_is_refused_and_logged(self):
        txn = _txn()
        before = len(txn.ledger)
        with pytest.raises(IllegalTransition):
            txn.transition_to(State.PAYMENT_COMPLETED, actor="t")
        assert txn.state is State.DRAFT
        assert len(txn.ledger) == before + 1

    def test_an_unknown_context_slot_is_refused(self):
        txn = _txn()
        with pytest.raises(ValueError, match="unknown context slot"):
            txn.attach_context("teleportation", {}, actor="t")


# --- memory retention ----------------------------------------------------


class TestMemoryRetentionAndScope:
    """§15 retention, §13 scope layering."""

    def test_default_retention_is_not_permanent(self):
        vault = MemoryVault("u")
        item = vault.remember(
            kind=PeoplePayNodeKind.USER_FACT,
            key="k",
            value="v",
            source=SourceType.SELF_REPORTED,
        )
        assert item.retention is Retention.TRANSACTION_ONLY

    def test_expiring_a_retention_class_removes_only_that_class(self):
        vault = MemoryVault("u")
        vault.remember(
            kind=PeoplePayNodeKind.USER_FACT,
            key="a",
            value=1,
            source=SourceType.SELF_REPORTED,
            retention=Retention.SESSION_ONLY,
        )
        vault.state_preference(key="b", value=2)
        assert vault.expire(Retention.SESSION_ONLY) == 1
        assert len(vault) == 1

    def test_the_four_scopes_are_queryable_separately(self):
        vault = MemoryVault("u")
        vault.remember(
            kind=PeoplePayNodeKind.USER_FACT,
            key="c",
            value=1,
            source=SourceType.SELF_REPORTED,
            scope=MemoryScope.CONVERSATION,
            transaction_id="txn-1",
        )
        vault.state_preference(key="p", value=2)
        assert len(vault.get_conversation_memory("txn-1")) == 1
        assert len(vault.get_user_memory()) == 1

    def test_an_unknown_scope_is_refused(self):
        vault = MemoryVault("u")
        with pytest.raises(ValueError, match="unknown memory scope"):
            vault.remember(
                kind=PeoplePayNodeKind.USER_FACT,
                key="k",
                value="v",
                source=SourceType.SELF_REPORTED,
                scope="everywhere",
            )

    def test_forgetting_a_scope_leaves_other_scopes(self):
        vault = MemoryVault("u")
        vault.remember(
            kind=PeoplePayNodeKind.USER_FACT,
            key="c",
            value=1,
            source=SourceType.SELF_REPORTED,
            scope=MemoryScope.CONVERSATION,
        )
        vault.state_preference(key="p", value=2)
        assert vault.forget_scope(MemoryScope.CONVERSATION) == 1
        assert len(vault.preferences()) == 1


# --- language ------------------------------------------------------------


class TestLanguageAndCurrency:
    """§22 multilingual handling, and that INR remains the default."""

    def test_pure_tamil_is_detected(self):
        from beacon.peoplepay import detect_language

        assert detect_language("எனக்கு ஒரு நல்ல கணினி வேண்டும்") == "ta"

    def test_tamil_mixed_with_a_latin_product_word_is_tanglish(self):
        """The demo utterance contains "laptop", so it is genuinely mixed script.

        Reporting ``ta`` here would overstate what was detected; the point of a
        distinct ``ta-Latn`` tag is that this case is neither Tamil nor English.
        """
        from beacon.peoplepay import detect_language

        assert detect_language(TAMIL) == "ta-Latn"

    def test_tanglish_is_its_own_tag(self):
        from beacon.peoplepay import detect_language

        assert detect_language(TANGLISH) == "ta-Latn"

    def test_english_is_detected(self):
        from beacon.peoplepay import detect_language

        assert detect_language("find me a laptop") == "en"

    def test_no_signal_returns_undetermined_not_a_guess(self):
        from beacon.peoplepay import detect_language

        assert detect_language("12345") == "und"

    def test_budget_parses_from_tamil_with_rupee_sign(self):
        from beacon.peoplepay import parse_budget

        assert parse_budget(TAMIL) == Money.of("50000", "INR")

    def test_budget_is_none_when_unstated_rather_than_zero(self):
        from beacon.peoplepay import parse_budget

        assert parse_budget("எனக்கு laptop வேணும்") is None

    def test_intent_mandate_still_defaults_to_inr(self):
        mandate = IntentMandate.create(
            user_id="u", raw_utterance=TAMIL, product_query="laptop"
        )
        assert mandate.currency == "INR"

    def test_money_still_refuses_floats(self):
        with pytest.raises(TypeError):
            Money.of(50000.0, "INR")

    def test_transaction_type_is_a_value_not_a_class(self):
        for t in (TransactionType.TRANSPORT, TransactionType.EXAM):
            txn = _txn(transaction_type=t)
            assert type(txn).__name__ == "Transaction"
            assert txn.transaction_type is t
