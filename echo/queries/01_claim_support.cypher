MATCH (claim:Claim {id: $claim_id})-[:SUPPORTED_BY]->(evidence:Evidence)
MATCH (evidence)-[:FROM_SOURCE]->(source:Source)
WHERE evidence.active = true AND source.active = true
  AND (evidence.valid_from IS NULL OR evidence.valid_from <= $as_of)
  AND (evidence.valid_until IS NULL OR evidence.valid_until > $as_of)
  AND (evidence.observed_at IS NULL OR evidence.observed_at <= $as_of)
RETURN claim.id AS claim_id,
       count(DISTINCT evidence) AS apparent_support_count,
       count(DISTINCT source) AS source_url_count,
       collect(DISTINCT evidence.agent_run_id) AS agent_run_ids
