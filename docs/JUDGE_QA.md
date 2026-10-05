# PeoplePay ECHO judge Q&A

## What is PeoplePay building?

PeoplePay is an **evidence-aware transaction operating system for AI agents**.
Its specialist apps can discover or analyze options, while ECHO provides the
canonical provenance graph and evidence-backed decision layer. The PeoplePay
Gateway mediates user intent, approvals, and the transaction journey.

## What is ECHO's role?

An agent or extension proposes claims and supporting evidence. ECHO validates
the envelope and provenance, correlates recorded source paths, applies policy,
and explains a recommendation or abstention. Extensions do not write canonical
graph truth or authorize a purchase.

## How does it fit the current projects?

- **GreenChain:** supplier sourcing and sustainability intelligence; currently
  deferred pending license and data/model rights review.
- **InflationForge:** price context; a narrow read-only ECHO adapter exists,
  disabled by default, and its city basket observations are not merchant quotes.
- **PROXY:** after-sales dispute evidence and draft preparation; deferred.
- **Rumi:** room and furniture discovery; deferred.
- **Beacon:** platform operations and incident response.
- **InHeir.AI:** property/legal vertical.
- **PeoplePay Gateway:** user intent, transaction records, and future merchant
  connectors.

The integrated directory links separate services. Shared login, storage, and
data exchange are not implied. See the [capability map](unified-product-plan.md).

## What changes in the ECHO demonstration?

The raw score winner is Alpha (94). Its eight observations traverse to one
recorded provenance root. Beta's raw score is 87, with three explicit roots;
the demonstration policy gives Beta 85 and Alpha 71, so Beta is recommended.
Two synthetic providers also submit repeated Alpha observations through the
same extension flow; they do not create extra roots. All names, URLs, and
observations are invented and use `.example` domains.

## Does ECHO prove sources are independent or true?

No. It counts recorded provenance roots when explicit dependency edges exist.
It does not establish truth, hidden copying, domain ownership, exact SKU fit,
or statistical independence. Missing links can overstate source diversity.
Unknown or unresolved paths can instead force the system to abstain.

## How does commerce authority work?

PeoplePay controls its user-authorized handoffs and transaction workspace.
ECHO does not make purchases. A merchant and its payment provider remain the
source of truth for merchant pricing, payment, and order outcomes. OpenAI's
[Agentic Checkout Spec](https://developers.openai.com/commerce/specs/checkout)
illustrates create/update/complete checkout sessions and order events handled
against a merchant's existing systems. PeoplePay has not implemented that
protocol or another live merchant checkout connector yet.

## What is built and what is next?

ECHO has a local FalkorDB graph, authenticated owner-scoped APIs when the
Gateway signing secret is configured, reviewed extension manifests/runtime,
synthetic graph demos, and a read-only InflationForge adapter. The next
milestone is **PeoplePay Extension SDK v1**: Python types, remote-service
scaffold, manifest lint, conformance tests, and a reference provider so future
capabilities can be added behind the contract without granting them core
authority.

The 15-case local benchmark measures explicit synthetic graph variations; it
does not establish provider quality. Production SSO, multi-worker approval
coordination, GreenChain/PROXY/Rumi adapters, organization policy, live checkout,
refund, and fulfillment integrations remain future work. The current Gateway
checkout is unavailable and sandbox orders move no money.
