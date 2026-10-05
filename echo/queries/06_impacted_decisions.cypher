MATCH (source:Source {id: $source_id})
MATCH (decision:Decision)-[:CONSIDERED]->(candidate:DecisionCandidate)-[:USED_SOURCE]->(source)
OPTIONAL MATCH (decision)-[:CREATED]->(transaction:Transaction)
RETURN DISTINCT decision.id AS decision_id,
       transaction.id AS transaction_id,
       transaction.gateway_state AS transaction_state

