MATCH (claim:Claim {requirement_id: $requirement_id})-[:SUPPORTED_BY]->(evidence:Evidence)
MATCH (evidence)-[:FROM_SOURCE]->(source:Source)
WHERE evidence.active = true AND source.active = true
  AND (evidence.valid_from IS NULL OR evidence.valid_from <= $as_of)
  AND (evidence.valid_until IS NULL OR evidence.valid_until > $as_of)
  AND (evidence.observed_at IS NULL OR evidence.observed_at <= $as_of)
OPTIONAL MATCH path=(source)-[:DERIVED_FROM|CITES|MIRRORS*0..8]->(root:Source)
WHERE NOT (root)-[:DERIVED_FROM|CITES|MIRRORS]->()
  AND all(n IN nodes(path) WHERE n.active = true
          AND (n.provenance_state = 'KNOWN' OR n.demo_scope IS NOT NULL))
RETURN evidence.agent_run_id AS agent_run_id,
       collect(DISTINCT root.id) AS provenance_roots
