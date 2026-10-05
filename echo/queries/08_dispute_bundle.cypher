MATCH (decision:Decision)-[:CREATED]->(transaction:Transaction {id: $transaction_id})
MATCH (decision)-[:CONSIDERED]->(candidate:DecisionCandidate)
RETURN decision, transaction, candidate,
       candidate.evidence_snapshot_json AS decision_evidence_snapshot_json
