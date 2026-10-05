MATCH (supplier:Supplier)-[:HAS_CLAIM]->(claim:Claim {requirement_id: $requirement_id})
MATCH (claim)-[:SUPPORTED_BY]->(evidence:Evidence)-[:FROM_SOURCE]->(source:Source)
WHERE evidence.active = true AND source.active = true
  AND (evidence.valid_from IS NULL OR evidence.valid_from <= $as_of)
  AND (evidence.valid_until IS NULL OR evidence.valid_until > $as_of)
  AND (evidence.observed_at IS NULL OR evidence.observed_at <= $as_of)
OPTIONAL MATCH (extension_run:ExtensionRun)-[:OBSERVED]->(evidence)
OPTIONAL MATCH scan=(source)-[:DERIVED_FROM|CITES|MIRRORS*0..8]->(unresolved:Source)
WHERE unresolved.active IS NULL OR unresolved.active <> true
   OR (unresolved.provenance_state IS NULL AND unresolved.demo_scope IS NULL)
   OR (unresolved.provenance_state <> 'KNOWN' AND unresolved.demo_scope IS NULL)
   OR (length(scan) = 8 AND (unresolved)-[:DERIVED_FROM|CITES|MIRRORS]->())
   OR any(n IN nodes(scan) WHERE size([m IN nodes(scan) WHERE m.id = n.id]) > 1)
OPTIONAL MATCH path=(source)-[:DERIVED_FROM|CITES|MIRRORS*0..8]->(root:Source)
WHERE NOT (root)-[:DERIVED_FROM|CITES|MIRRORS]->()
  AND all(n IN nodes(path) WHERE n.active = true
          AND (n.provenance_state = 'KNOWN' OR n.demo_scope IS NOT NULL))
OPTIONAL MATCH (policy:CandidatePolicy {requirement_id: $requirement_id, supplier_id: supplier.id})
WHERE policy.active = true
RETURN supplier.id AS supplier_id,
       supplier.name AS supplier_name,
       coalesce(policy.raw_score, CASE WHEN supplier.demo_scope IS NOT NULL THEN supplier.raw_score ELSE NULL END) AS raw_score,
       claim.id AS claim_id,
       count(DISTINCT evidence) AS apparent_support_count,
       count(DISTINCT root) AS provenance_root_count,
       count(DISTINCT source) AS distinct_source_count,
       avg(evidence.confidence) AS mean_confidence,
       collect(DISTINCT root.id) AS root_source_ids,
       collect(DISTINCT {evidence_id: evidence.id,
                         source_id: source.id,
                         source_url: source.source_url,
                         root_source_id: root.id,
                         path_source_ids: [n IN nodes(path) | n.id],
                         dependency_edge_ids: [relationship IN relationships(path) | relationship.id],
                         agent_run_id: evidence.agent_run_id,
                         extension_run_id: extension_run.id,
                         confidence: evidence.confidence,
                         observed_at: evidence.observed_at,
                         valid_from: evidence.valid_from,
                         valid_until: evidence.valid_until,
                         snapshot_id: evidence.snapshot_id,
                         content_hash: evidence.content_hash,
                         provenance_state: source.provenance_state,
                         lineage_unresolved: unresolved.id IS NOT NULL
                           OR ((evidence.provenance_state IS NULL
                                OR evidence.provenance_state <> 'KNOWN'
                                OR evidence.observed_at IS NULL)
                               AND evidence.demo_scope IS NULL)
                           OR coalesce(claim.conflict_open, false)
                           OR coalesce(claim.kind = 'model_output', false)
                           OR coalesce(evidence.verification_state = 'MODEL_OUTPUT', false)}) AS evidence_paths,
       supplier.identity_status AS identity_status,
       (policy.raw_score IS NOT NULL OR supplier.demo_scope IS NOT NULL) AS policy_available

