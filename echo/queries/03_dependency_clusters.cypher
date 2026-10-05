MATCH (source:Source)
WHERE source.demo_scope = $demo_scope AND source.active = true
MATCH path=(source)-[:DERIVED_FROM|CITES|MIRRORS*1..8]->(root:Source)
WHERE NOT (root)-[:DERIVED_FROM|CITES|MIRRORS]->()
  AND all(n IN nodes(path) WHERE n.active = true)
RETURN root.id AS root_source_id,
       collect(DISTINCT source.id) AS dependent_source_ids,
       collect(DISTINCT type(relationships(path)[0])) AS observed_edge_types
