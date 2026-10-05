# PeoplePay as one product

**Product direction:** one PeoplePay front door and transaction record, backed by focused services that keep their own runtime, data, and permissions.

## What the user experiences

PeoplePay is a procurement and transaction workspace. A user begins with a need, finds and compares options, reviews the evidence and uncertainty, saves a decision to a transaction, and can later follow its order record or prepare a dispute. Specialist workspaces are available from one directory; the transaction workspace remains the durable user journey.

```text
Need or product idea
    ├── ECHO: audit evidence lineage and explain supplier decisions
    ├── GreenChain: discover and compare suppliers and environmental estimates
    ├── Rumi: plan a room and discover furniture
    └── InflationForge: inspect applicable regional price trends
                    ↓ user reviews the options
PeoplePay transaction: record the chosen plan, user-entered cart, and evidence
                    ↓ order issue, when requested
PROXY: organize evidence and prepare a user-reviewed dispute draft

Separate specialist areas:
InHeir.AI: property cases and reports
Beacon: platform operator incident response
```

The user approves each handoff. Discovery, design, a plan, and a transaction are different actions. A model or supplier ranking cannot authorize a purchase. Property and operations tools are available in the same suite but are not inserted into a consumer purchase flow without a reason.

## Current implementation in this checkout

- The gateway serves the PeoplePay transaction workspace and now displays a directory for ECHO, GreenChain, Rumi, InflationForge, InHeir.AI, PROXY, and Beacon.
- Module destinations are configured on the gateway server with `PEOPLEPAY_GREENCHAIN_URL`, `PEOPLEPAY_RUMI_URL`, `PEOPLEPAY_INFLATIONFORGE_URL`, `PEOPLEPAY_INHEIR_URL`, `PEOPLEPAY_PROXY_URL`, and `PEOPLEPAY_BEACON_URL`.
- A configured destination opens in a separate tab. An unconfigured service is visibly disabled; the directory does not claim that a service is running or authenticated.
- The gateway still owns transaction records, carts, sandbox order records, evidence, and activity. Module destinations do not yet provide shared sign-in or transfer data into a transaction.
- ECHO is a separate FastAPI service backed by a dedicated FalkorDB graph. Its synthetic demo traverses explicit citation/derivation edges and demonstrably changes the raw-score winner. The API can create a Gateway planning record after explicit human confirmation for non-demo decisions; it cannot execute checkout. Authentication for the ECHO API and general source/evidence ingestion are not implemented.
- GreenChain can discover and score supplier candidates, but its documented roadmap still lists unit cost integration as future work. Its environmental estimates and public web findings must retain their source and uncertainty. They are not verified supplier certifications or purchase prices.
- GreenChain's README claims MIT, but the added checkout contains no LICENSE file. Confirm the grant, attribution, and rights to redistribute its datasets and model artifacts before copying GreenChain source into another distributable package.

## Integration sequence

1. **One front door — implemented:** expose the specialist workspaces from the transaction gateway, with server-configured links and honest unavailable states.
2. **ECHO evidence handoff — next:** define an authenticated, versioned source and evidence ingestion contract. Preserve snapshots, hashes, timestamps, dependency explanations, contradictions, SKU scope, and human review state. Validate the current scoring policy against real labeled data before using it for procurement.
3. **GreenChain decision handoff — next:** define a versioned, user-approved supplier comparison payload. Preserve candidate identity, source URLs, search time, scoring assumptions, transport mode, and score uncertainty. Attach it to a transaction as research evidence; do not create a priced cart from emissions scores.
4. **Rumi plan handoff — after rights and API review:** send the user's approved room plan and selected items as evidence. Keep geometry validation and unknown dimensions explicit. Create cart lines only when product, variant, price, currency, and merchant source are known.
5. **Price and evidence adapters:** connect InflationForge only when its US city-basket observations apply. Preserve USD and observation provenance; never treat basket inflation as a merchant quote. Add property and dispute handoffs with explicit user selection and data minimization.
6. **Shared identity and deployment:** establish one identity provider and deployment gateway, while each service retains its own authorization checks, database, and secrets. Enforce an allowlist for service URLs and browser origins.
7. **Real commerce:** select a payment provider, implement hosted payment and order APIs, reconciliation, cancellation, and refund flows. Until then, checkout remains unavailable and sandbox records move no money.

## Boundaries that keep it one product without forcing one codebase

- The gateway is the source of truth for transaction ownership, user intent, permissions, and audit history.
- Specialist services own their domain data and model calls. The gateway stores references and user-approved evidence, not copies of private specialist databases.
- Every handoff uses a versioned JSON contract with provenance, timestamps, currency, and explicit evidence quality.
- External search results, ML estimates, manually entered prices, sandbox actions, and verified provider data remain distinct evidence classes.
- No service URL, API key, or provider secret is placed in browser code or model context.
- Keep individual dependency environments and deploy each service independently. A shared navigation shell is not shared authentication; SSO remains a separate integration task.

## Release truth

The module directory is a connected entry point, not proof that all six applications are deployed, share accounts, or exchange records. The end state is one product journey and one transaction history with specialist capabilities connected through reviewed contracts. Production payment, shared identity, and several data handoffs still require implementation and verification.
