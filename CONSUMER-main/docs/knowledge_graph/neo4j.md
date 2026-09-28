# Neo4j Knowledge Graph

Graph purpose: preserve institutional memory and discover patterns across cases without exposing user identity.

Core nodes:

- `User` anonymous/internal reference only
- `Case`
- `Institution`
- `Domain`
- `Document`
- `Evidence`
- `PolicyClause`
- `Regulation`
- `Appeal`
- `Outcome`

Core relationships:

- `(Case)-[:AGAINST]->(Institution)`
- `(Case)-[:IN_DOMAIN]->(Domain)`
- `(Case)-[:SUPPORTED_BY]->(Evidence)`
- `(Evidence)-[:EXTRACTED_FROM]->(Document)`
- `(Appeal)-[:CITES]->(PolicyClause|Regulation)`
- `(Case)-[:RESULTED_IN]->(Outcome)`

Healthcare starts with insurance-denial patterns. Other domains add their own evidence and regulation node types as needed.
