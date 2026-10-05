MATCH (decision:Decision {id: $decision_id})
OPTIONAL MATCH (decision)-[:CONSIDERED]->(candidate:DecisionCandidate)
RETURN decision.id AS decision_id,
       decision.status AS decision_status,
       decision.recommended_supplier_id AS recommended_supplier_id,
       candidate.id AS candidate_id,
       candidate.supplier_id AS supplier_id,
       candidate.supplier_name AS supplier_name,
       candidate.raw_score AS raw_score,
       candidate.robust_score AS robust_score,
       candidate.evidence_snapshot_json AS evidence_trace

