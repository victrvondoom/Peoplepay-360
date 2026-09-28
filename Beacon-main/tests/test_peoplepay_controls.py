"""Executable gates for PeoplePay's transaction-wide controls."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from beacon.assurance import EvidenceClass, Money, utcnow
from beacon.peoplepay import (
    BudgetExceeded,
    CartLine,
    CheckoutSnapshot,
    ClaimStatus,
    CommunityAggregator,
    ConditionalGrant,
    ConsentLedger,
    ConsentPurpose,
    CostBudget,
    EvidenceGate,
    EvidenceRequirement,
    ExperienceContribution,
    MandateCapsule,
    MandateError,
    MandateIssuer,
    MandateReplay,
    PeoplePayNodeKind,
    Permission,
    RiskDisposition,
    RiskEngine,
    SourceType,
    SubstitutionPolicy,
    Transaction,
    TransactionType,
    UsageMeter,
)


def _transaction(*, ceiling: str = "50000") -> Transaction:
    transaction = Transaction.create(
        user_id="user-1",
        raw_utterance="Buy the approved room plan under INR 50,000",
    )
    transaction.grant_conditional(
        ConditionalGrant(
            permission=Permission.PAYMENT,
            max_amount=Money.of(ceiling, "INR"),
            raw_utterance="Pay up to the stated ceiling",
        ),
        actor="user-1",
    )
    return transaction


def _checkout(
    *,
    price: str = "40000",
    merchant: str = "merchant-1",
    variant: str = "oak",
) -> CheckoutSnapshot:
    return CheckoutSnapshot.create(
        (
            CartLine(
                line_id="line-1",
                merchant_id=merchant,
                product_id="desk-1",
                variant_id=variant,
                quantity=1,
                unit_price=Money.of(price, "INR"),
            ),
        ),
        shipping=Money.of("500", "INR"),
        tax=Money.zero("INR"),
    )


class TestMandateCapsule:
    def test_valid_capsule_binds_exact_checkout(self):
        transaction = _transaction()
        checkout = _checkout()
        issuer = MandateIssuer(b"k" * 32)

        capsule = issuer.issue(transaction, checkout, actor="user-1")
        issuer.verify(
            capsule,
            checkout,
            transaction_id=transaction.transaction_id,
            user_id=transaction.user_id,
        )

        assert capsule.max_total == checkout.total
        assert capsule.substitution_policy is SubstitutionPolicy.NONE
        assert len(transaction.graph.nodes) == 1

        restored = MandateCapsule.from_dict(capsule.to_dict())
        issuer.verify(
            restored,
            checkout,
            transaction_id=transaction.transaction_id,
            user_id=transaction.user_id,
        )

    def test_changed_variant_requires_fresh_consent(self):
        transaction = _transaction()
        issuer = MandateIssuer(b"k" * 32)
        capsule = issuer.issue(transaction, _checkout(), actor="user-1")

        with pytest.raises(MandateError, match="cart was not approved"):
            issuer.verify(
                capsule,
                _checkout(variant="walnut"),
                transaction_id=transaction.transaction_id,
                user_id=transaction.user_id,
            )

    def test_tampering_breaks_signature(self):
        transaction = _transaction()
        checkout = _checkout()
        issuer = MandateIssuer(b"k" * 32)
        capsule = issuer.issue(transaction, checkout, actor="user-1")
        tampered = replace(capsule, max_total=Money.of("90000", "INR"))

        with pytest.raises(MandateError, match="signature"):
            issuer.verify(
                tampered,
                checkout,
                transaction_id=transaction.transaction_id,
                user_id=transaction.user_id,
            )

    def test_capsule_is_single_use(self):
        transaction = _transaction()
        checkout = _checkout()
        issuer = MandateIssuer(b"k" * 32)
        capsule = issuer.issue(transaction, checkout, actor="user-1")

        issuer.consume(
            capsule,
            checkout,
            transaction_id=transaction.transaction_id,
            user_id=transaction.user_id,
        )
        with pytest.raises(MandateReplay):
            issuer.consume(
                capsule,
                checkout,
                transaction_id=transaction.transaction_id,
                user_id=transaction.user_id,
            )

    def test_expired_capsule_is_refused(self):
        transaction = _transaction()
        checkout = _checkout()
        issuer = MandateIssuer(b"k" * 32)
        capsule = issuer.issue(transaction, checkout, actor="user-1")

        with pytest.raises(MandateError, match="expired"):
            issuer.verify(
                capsule,
                checkout,
                transaction_id=transaction.transaction_id,
                user_id=transaction.user_id,
                now=capsule.expires_at,
            )

    def test_only_explicit_alternative_hashes_are_valid(self):
        transaction = _transaction()
        original = _checkout(price="40000", variant="oak")
        alternative = _checkout(price="39000", variant="walnut")
        issuer = MandateIssuer(b"k" * 32)
        capsule = issuer.issue(
            transaction,
            original,
            actor="user-1",
            approved_alternatives=(alternative,),
        )

        issuer.verify(
            capsule,
            alternative,
            transaction_id=transaction.transaction_id,
            user_id=transaction.user_id,
        )
        assert capsule.substitution_policy is SubstitutionPolicy.EXPLICIT_ALTERNATIVES

    def test_sandbox_evidence_cannot_authorize_real_payment(self):
        transaction = _transaction()
        transaction.add_evidence(
            kind=PeoplePayNodeKind.PRICE_OBSERVATION,
            actor="test",
            source="sandbox",
            source_type=SourceType.SANDBOX,
            sandbox=True,
        )
        issuer = MandateIssuer(b"k" * 32)

        with pytest.raises(MandateError, match="sandbox"):
            issuer.issue(transaction, _checkout(), actor="user-1")


class TestRiskAdaptiveAutonomy:
    def test_reversible_discovery_is_allowed(self):
        result = RiskEngine(specialist_threshold=Money.of("100000", "INR")).assess(
            transaction_type=TransactionType.PURCHASE,
            amount=None,
            consequential=False,
        )
        assert result.disposition is RiskDisposition.ALLOW

    def test_consequential_action_requires_confirmation(self):
        result = RiskEngine(specialist_threshold=Money.of("100000", "INR")).assess(
            transaction_type=TransactionType.PURCHASE,
            amount=Money.of("1000", "INR"),
            evidence_classes=(EvidenceClass.VERIFIED,),
            consequential=True,
        )
        assert result.disposition is RiskDisposition.REQUIRE_CONFIRMATION

    @pytest.mark.parametrize(
        "evidence_class",
        [
            EvidenceClass.UNKNOWN,
            EvidenceClass.UNAVAILABLE,
            EvidenceClass.CONFLICTING,
            EvidenceClass.STALE,
            EvidenceClass.SANDBOX,
        ],
    )
    def test_bad_evidence_blocks_consequential_action(self, evidence_class):
        result = RiskEngine(specialist_threshold=Money.of("100000", "INR")).assess(
            transaction_type=TransactionType.PURCHASE,
            amount=Money.of("1000", "INR"),
            evidence_classes=(evidence_class,),
            consequential=True,
        )
        assert result.disposition is RiskDisposition.BLOCK

    def test_property_and_high_value_actions_require_specialist(self):
        engine = RiskEngine(specialist_threshold=Money.of("100000", "INR"))
        property_result = engine.assess(
            transaction_type=TransactionType.PROPERTY,
            amount=Money.of("1000", "INR"),
            consequential=False,
        )
        high_value_result = engine.assess(
            transaction_type=TransactionType.PURCHASE,
            amount=Money.of("100000", "INR"),
            consequential=False,
        )
        assert property_result.disposition is RiskDisposition.REQUIRE_SPECIALIST
        assert high_value_result.disposition is RiskDisposition.REQUIRE_SPECIALIST


class TestProductTruthPassport:
    def _add_price(
        self,
        transaction: Transaction,
        *,
        source: str,
        value: int,
        evidence_class: EvidenceClass = EvidenceClass.VERIFIED,
        sandbox: bool = False,
    ) -> None:
        observation = transaction.observation(
            field_name="price_minor",
            value=value,
            source=source,
            source_type=(
                SourceType.SANDBOX if sandbox else SourceType.PRIMARY_SOURCE
            ),
            evidence_class=evidence_class,
            sandbox=sandbox,
        )
        transaction.add_evidence(
            PeoplePayNodeKind.PRICE_OBSERVATION,
            actor="market",
            source=source,
            source_type=(
                SourceType.SANDBOX if sandbox else SourceType.PRIMARY_SOURCE
            ),
            observations=(observation,),
            sandbox=sandbox,
        )

    def test_fresh_corroborated_claim_passes_and_is_recorded(self):
        transaction = _transaction()
        self._add_price(transaction, source="merchant", value=499900)
        self._add_price(transaction, source="catalog", value=499900)

        passport = EvidenceGate().evaluate(
            transaction,
            (
                EvidenceRequirement(
                    field="price_minor",
                    max_age=timedelta(minutes=10),
                    min_sources=2,
                ),
            ),
            actor="policy",
        )

        assert passport.decision_grade is True
        assert passport.checks[0].status is ClaimStatus.PASS
        assert len(transaction.graph.edges) == 2

    def test_missing_stale_and_sandbox_claims_block(self):
        missing = _transaction()
        missing_passport = EvidenceGate().evaluate(
            missing,
            (EvidenceRequirement("stock", timedelta(minutes=5)),),
            actor="policy",
        )
        assert missing_passport.checks[0].evidence_class is EvidenceClass.UNKNOWN

        stale = _transaction()
        self._add_price(stale, source="merchant", value=499900)
        stale_passport = EvidenceGate().evaluate(
            stale,
            (EvidenceRequirement("price_minor", timedelta(minutes=5)),),
            actor="policy",
            now=utcnow() + timedelta(minutes=6),
        )
        assert stale_passport.decision_grade is False
        assert stale_passport.checks[0].evidence_class is EvidenceClass.STALE

        sandbox = _transaction()
        self._add_price(
            sandbox,
            source="fixture",
            value=499900,
            sandbox=True,
        )
        sandbox_passport = EvidenceGate().evaluate(
            sandbox,
            (EvidenceRequirement("price_minor", timedelta(minutes=5)),),
            actor="policy",
        )
        assert sandbox_passport.decision_grade is False
        assert sandbox_passport.checks[0].evidence_class is EvidenceClass.SANDBOX

    def test_disagreeing_sources_are_an_explicit_conflict(self):
        transaction = _transaction()
        self._add_price(transaction, source="merchant", value=499900)
        self._add_price(transaction, source="catalog", value=599900)

        passport = EvidenceGate().evaluate(
            transaction,
            (EvidenceRequirement("price_minor", timedelta(minutes=5)),),
            actor="policy",
        )

        assert passport.decision_grade is False
        assert passport.checks[0].evidence_class is EvidenceClass.CONFLICTING

    def test_unverified_claim_requires_explicitly_weaker_policy(self):
        transaction = _transaction()
        self._add_price(
            transaction,
            source="listing",
            value=499900,
            evidence_class=EvidenceClass.UNVERIFIED,
        )
        strict = EvidenceGate().evaluate(
            transaction,
            (EvidenceRequirement("price_minor", timedelta(minutes=5)),),
            actor="policy",
        )
        permissive = EvidenceGate().evaluate(
            transaction,
            (
                EvidenceRequirement(
                    "price_minor",
                    timedelta(minutes=5),
                    require_verified=False,
                ),
            ),
            actor="policy",
        )
        assert strict.decision_grade is False
        assert permissive.decision_grade is True


class TestEconomicGovernor:
    def test_usage_is_claimed_within_hard_limits(self):
        meter = UsageMeter(
            CostBudget(
                max_provider_cost=Money.of("10", "INR"),
                max_model_calls=2,
                max_search_calls=3,
                max_external_calls=4,
                max_latency_ms=5000,
            )
        )
        meter.consume(
            provider_cost=Money.of("2.50", "INR"),
            model_calls=1,
            search_calls=2,
            external_calls=1,
            latency_ms=300,
        )
        assert meter.provider_cost == Money.of("2.50", "INR")

    def test_rejected_claim_does_not_mutate_usage(self):
        meter = UsageMeter(
            CostBudget(
                max_provider_cost=Money.of("1", "INR"),
                max_model_calls=1,
                max_search_calls=1,
                max_external_calls=1,
                max_latency_ms=100,
            )
        )
        with pytest.raises(BudgetExceeded):
            meter.consume(model_calls=2)
        assert meter.model_calls == 0


class TestConsentAndCommunityPrivacy:
    def _grant_review(self, ledger: ConsentLedger, user_id: str) -> None:
        ledger.grant(
            user_id=user_id,
            purpose=ConsentPurpose.COMMUNITY_REVIEW,
            fields=("rating", "ownership_days", "verified_purchase"),
            notice="Share an anonymous product experience",
            raw_confirmation="I agree",
        )

    def test_consent_is_purpose_bound_and_revocable(self):
        ledger = ConsentLedger()
        receipt = ledger.grant(
            user_id="u1",
            purpose=ConsentPurpose.SHARE_PRICE,
            fields=("price",),
            notice="Share price anonymously",
            raw_confirmation="Share my price",
        )
        assert ledger.allows(
            user_id="u1",
            purpose=ConsentPurpose.SHARE_PRICE,
            fields=("price",),
        )
        assert not ledger.allows(
            user_id="u1",
            purpose=ConsentPurpose.SHARE_PURCHASE_DATE,
            fields=("purchased_on",),
        )
        ledger.revoke(receipt.consent_id)
        assert not ledger.allows(
            user_id="u1",
            purpose=ConsentPurpose.SHARE_PRICE,
            fields=("price",),
        )

    def test_expired_consent_is_not_active(self):
        ledger = ConsentLedger()
        receipt = ledger.grant(
            user_id="u1",
            purpose=ConsentPurpose.MEMORY,
            fields=("room_style",),
            notice="Remember room style",
            raw_confirmation="Remember this",
            expires_at=utcnow() + timedelta(minutes=1),
        )
        assert not ledger.allows(
            user_id="u1",
            purpose=ConsentPurpose.MEMORY,
            fields=("room_style",),
            now=receipt.expires_at,
        )

    def test_small_cohort_is_suppressed_and_identity_never_returns(self):
        ledger = ConsentLedger()
        aggregator = CommunityAggregator(ledger, min_cohort=3)
        for number in range(3):
            user_id = f"u{number}"
            self._grant_review(ledger, user_id)
            aggregator.contribute(
                ExperienceContribution(
                    contributor_id=user_id,
                    product_id="chair-1",
                    rating=number + 3,
                    ownership_days=30,
                    verified_purchase=True,
                )
            )
            if number < 2:
                assert aggregator.aggregate("chair-1")["status"] == (
                    "SUPPRESSED_SMALL_COHORT"
                )

        result = aggregator.aggregate("chair-1")
        assert result["status"] == "AVAILABLE"
        assert result["average_rating"] == "4.00"
        assert "contributor_id" not in result

    def test_price_and_date_need_separate_consent(self):
        ledger = ConsentLedger()
        self._grant_review(ledger, "u1")
        aggregator = CommunityAggregator(ledger, min_cohort=2)
        contribution = ExperienceContribution(
            contributor_id="u1",
            product_id="chair-1",
            rating=5,
            ownership_days=10,
            verified_purchase=True,
            price=Money.of("999", "INR"),
            purchased_on=date(2026, 1, 1),
        )
        with pytest.raises(PermissionError, match="price"):
            aggregator.contribute(contribution)

    def test_withdrawal_removes_future_aggregate_eligibility(self):
        ledger = ConsentLedger()
        aggregator = CommunityAggregator(ledger, min_cohort=2)
        receipts = []
        for user_id in ("u1", "u2"):
            receipts.append(
                ledger.grant(
                    user_id=user_id,
                    purpose=ConsentPurpose.COMMUNITY_REVIEW,
                    fields=("rating", "ownership_days", "verified_purchase"),
                    notice="Share an anonymous product experience",
                    raw_confirmation="I agree",
                )
            )
            aggregator.contribute(
                ExperienceContribution(
                    contributor_id=user_id,
                    product_id="chair-1",
                    rating=5,
                    ownership_days=30,
                    verified_purchase=True,
                )
            )
        assert aggregator.aggregate("chair-1")["status"] == "AVAILABLE"

        ledger.revoke(receipts[0].consent_id)
        assert aggregator.aggregate("chair-1")["status"] == (
            "SUPPRESSED_SMALL_COHORT"
        )
