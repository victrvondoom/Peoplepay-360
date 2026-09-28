"""PeoplePay -- the personal transaction layer over ``beacon.assurance``.

    one user, one memory, one transaction id, one agent, many capabilities

``beacon.assurance`` decides *whether* something may happen and records *what*
happened.  PeoplePay is what a person talks to, and what keeps their context
between one transaction and the next.

Phases implemented here:

    ``transaction``  Phase 1 -- the canonical ``Transaction`` aggregate
    ``nodes``        Phase 2 -- typed nodes, source types, visibility, retention
    ``authority``    Phase 2 -- separated permissions and transaction types
    ``memory``       Phase 3 -- the personal vault, mirroring PROXY's layering
    ``agent``        Phase 4 -- the thin shell and its nine controlled tools

Not here, deliberately: payment rails, booking execution, browser automation,
and the YouTube/Telegram/transport connectors.  Those are the next wave, and
§31 says the foundation must exist first.
"""

from __future__ import annotations

from beacon.peoplepay.agent import (
    AgentResponse,
    PeoplePayAgent,
    ResponseKind,
    ToolRegistry,
    detect_language,
    parse_budget,
)
from beacon.peoplepay.authority import (
    CONSEQUENTIAL_PERMISSIONS,
    AuthorityError,
    ConditionalGrant,
    PaymentMethod,
    Permission,
    PermissionSet,
    TransactionType,
)
from beacon.peoplepay.evidence_gate import (
    ClaimCheck,
    ClaimStatus,
    EvidenceGate,
    EvidencePassport,
    EvidenceRequirement,
)
from beacon.peoplepay.governance import (
    BudgetExceeded,
    CommunityAggregator,
    ConsentLedger,
    ConsentPurpose,
    ConsentReceipt,
    CostBudget,
    ExperienceContribution,
    RiskAssessment,
    RiskDisposition,
    RiskEngine,
    UsageMeter,
)
from beacon.peoplepay.mandate import (
    CartLine,
    CheckoutSnapshot,
    MandateCapsule,
    MandateError,
    MandateIssuer,
    MandateReplay,
    SubstitutionPolicy,
)
from beacon.peoplepay.memory import (
    MemoryItem,
    MemoryScope,
    MemoryVault,
    PromotionError,
    VisibilityError,
)
from beacon.peoplepay.nodes import (
    DECISION_CAPABLE_SOURCES,
    PERSONAL_NODE_KINDS,
    PeoplePayNodeKind,
    Retention,
    SourceType,
    Visibility,
)
from beacon.peoplepay.transaction import (
    CONTEXT_SLOTS,
    Transaction,
    TransactionOwnershipError,
)

__all__ = [
    "CONSEQUENTIAL_PERMISSIONS",
    "CONTEXT_SLOTS",
    "DECISION_CAPABLE_SOURCES",
    "PERSONAL_NODE_KINDS",
    "AgentResponse",
    "AuthorityError",
    "BudgetExceeded",
    "CartLine",
    "CheckoutSnapshot",
    "ClaimCheck",
    "ClaimStatus",
    "CommunityAggregator",
    "ConditionalGrant",
    "ConsentLedger",
    "ConsentPurpose",
    "ConsentReceipt",
    "CostBudget",
    "EvidenceGate",
    "EvidencePassport",
    "EvidenceRequirement",
    "ExperienceContribution",
    "MemoryItem",
    "MemoryScope",
    "MemoryVault",
    "MandateCapsule",
    "MandateError",
    "MandateIssuer",
    "MandateReplay",
    "PaymentMethod",
    "PeoplePayAgent",
    "PeoplePayNodeKind",
    "Permission",
    "PermissionSet",
    "PromotionError",
    "ResponseKind",
    "Retention",
    "RiskAssessment",
    "RiskDisposition",
    "RiskEngine",
    "SourceType",
    "ToolRegistry",
    "Transaction",
    "TransactionOwnershipError",
    "TransactionType",
    "SubstitutionPolicy",
    "UsageMeter",
    "Visibility",
    "VisibilityError",
    "detect_language",
    "parse_budget",
]
