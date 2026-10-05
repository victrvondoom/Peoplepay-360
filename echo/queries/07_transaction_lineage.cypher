MATCH (decision:Decision {id: $decision_id})
OPTIONAL MATCH (decision)-[:HAS_APPROVAL]->(approval:Approval)-[:APPROVED_BY]->(user:User)
OPTIONAL MATCH (decision)-[:CREATED]->(transaction:Transaction)
OPTIONAL MATCH (transaction)-[:CREATED_ORDER]->(order:Order)
OPTIONAL MATCH (order)-[:HAS_EVENT]->(event:DeliveryEvent)
RETURN decision, approval, user, transaction, order, event
