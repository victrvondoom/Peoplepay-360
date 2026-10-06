# Source of truth and authority

| State / capability | Owner | Other systems receive |
|---|---|---|
| Workflow correlation and minimized assistance facts | PeoplePay coordinator | Scoped facts with explicit consent; stable workflow ID |
| Assistance policy, eligibility engine and specialist graph | CivicMesh | Normalized program/rule references, criteria, estimates, next question, proposed steps/routes |
| Supplier discovery/environment estimates | GreenChain | Leads and estimates with provenance limitations |
| Price snapshots | InflationForge | Timestamped product/location/currency/source context, not merchant quotes |
| Room/design and discovery state | Rumi / Convex | Existing bounded design handoff; hosted workspace remains separate |
| Property/legal case and document state | InHeir / Azure / MongoDB | Existing bounded property capability; no automatic legal action |
| Canonical evidence, decision version and historical reasoning | ECHO / FalkorDB | Immutable decision ID/hash and normalized trace; provider internal graph is not copied |
| Approvals and controlled transaction lifecycle | PeoplePay Gateway | Version-bound authorized actions; extensions return proposals only |
| Cart, order, fulfillment and merchant acceptance | External merchant; reference merchant in sandbox | Checkout/order IDs and authenticated lifecycle events |
| Payment settlement | Merchant payment processor | External payment references; PeoplePay reference orders move no money |
| Consumer dispute drafts | PROXY | Correlated order/decision/evidence packet; native authenticated provider or explicitly labeled reference draft |
| Operations incidents/remediation | Beacon | Separate operator approval and assurance lifecycle |

No specialist service directly writes another service's database. CivicMesh service credentials are distinct from Gateway/merchant/model credentials. The local launcher passes an allowlisted environment to the deterministic service; its container receives only its dedicated token and optional policy date.

SSO, production payment rails, specialist graph federation and official benefits submission are future work. Local OPEN caller mode is development only.
