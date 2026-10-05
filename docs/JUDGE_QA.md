# ECHO judge Q&A

## What problem does ECHO address?

Agent agreement can exaggerate support when agents repeat pages that copied the same original. ECHO stores explicit `DERIVED_FROM`, `CITES`, and `MIRRORS` edges and counts terminal source roots for the evidence attached to each supplier claim.

## What changes in the demo?

The raw score winner is Alpha (94). Graph traversal finds eight observations but one provenance root. Applying the displayed policy gives Alpha 71. Beta's lower raw score (87) and three provenance roots produce 85, so the recommendation changes to Beta. Gamma is excluded because it has fewer than two roots.

## Is the demo based on real supplier data?

No. Supplier names, sources, URLs, observations, and scores are invented and use reserved `.example` domains. No supplier has been contacted and no market data has been fetched.

## Does ECHO prove sources are independent or true?

No. It counts graph-distinct roots only when a dependency is explicitly present. It does not infer hidden copying, verify source identity or truth, determine whether evidence applies to an exact SKU, or establish statistical independence. Missing edges can overstate diversity.

## Is ECHO a shared login, checkout, or payment system?

No. The product directory links separate apps. ECHO has no independent authentication in this prototype. Its approval API requires an explicit confirmation field and passes a planning request to the existing PeoplePay Gateway. The Gateway plan is not an order or payment. The demo decision is blocked from creating a real transaction.

## What is not built yet?

External sourcing feeds, URL ingestion and crawling, inferred dependency matching, freshness schedules, contradiction resolution, supplier identity/quote verification, full approval UI, durable cross-service event delivery, and a production identity/tenant boundary. Benchmark and adversarial performance claims are not available yet.
