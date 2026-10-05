MATCH (claim:Claim {id: $claim_id})-[:CONTRADICTS]-(other:Claim)
RETURN other.id AS contradicting_claim_id,
       other.predicate AS predicate,
       other.value AS value,
       other.created_at AS created_at
