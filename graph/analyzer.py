"""
Graph Analyzer

Provides analysis capabilities for the knowledge graph including:
- Trust propagation
- Risk scoring
- Supplier dependency analysis
- Recommendation generation
- Evidence intelligence
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import threading

from graph.models import (
    Entity,
    Relationship,
    EntityType,
    RelationshipType,
    TrustScore,
    RiskScore,
)
from graph.engine import get_graph_engine, GraphEngine
from graph.errors import GraphError, EntityNotFoundError


# Singleton instance
_analyzer_instance: Optional["GraphAnalyzer"] = None


class GraphAnalyzer:
    """
    Analyzes the knowledge graph for insights and intelligence.
    
    Capabilities:
    - Trust score calculation and propagation
    - Risk score calculation and propagation
    - Supplier dependency graph analysis
    - Connected transaction history analysis
    - Recommendation generation based on graph relationships
    - Evidence-backed decision support
    """
    
    def __init__(self, engine: Optional[GraphEngine] = None):
        """Initialize the graph analyzer."""
        self.engine = engine or get_graph_engine()
        self._trust_cache: Dict[str, TrustScore] = {}
        self._risk_cache: Dict[str, RiskScore] = {}
        self._lock = threading.Lock()
    
    # Trust Analysis
    
    def calculate_trust_score(
        self,
        entity_id: str,
        max_depth: int = 3,
    ) -> TrustScore:
        """
        Calculate trust score for an entity based on its relationships.
        
        Uses a weighted average approach where trust propagates through
        relationships with decay based on distance.
        
        Args:
            entity_id: The entity to calculate trust for
            max_depth: How many relationship hops to consider
            
        Returns:
            TrustScore with computed trust value
        """
        with self._lock:
            cache_key = f"{entity_id}:{max_depth}"
            if cache_key in self._trust_cache:
                return self._trust_cache[cache_key]
        
        entity = self.engine.get_entity(entity_id)
        if not entity:
            raise EntityNotFoundError(entity_id)
        
        # Start with base trust from entity properties
        base_trust = entity.properties.get("trust_score", 0.5)
        
        # Get all related entities with their trust relationships
        related = self.engine.get_related_entities(
            entity_id=entity_id,
            relationship_type=RelationshipType.TRUSTS,
            max_depth=max_depth,
        )
        
        total_weight = 0.0
        weighted_sum = 0.0
        evidence_ids: List[str] = []
        reasons: List[str] = []
        
        # Process trust relationships
        for other_id, (other_entity, relationships) in related.items():
            for rel in relationships:
                if rel.relationship_type == RelationshipType.TRUSTS:
                    other_trust = self._get_cached_trust(other_id, max_depth - 1)
                    weight = rel.weight * (0.5 ** (rel.properties.get("depth", 1)))
                    weighted_sum += other_trust.score * weight
                    total_weight += weight
                    evidence_ids.extend(other_trust.evidence_ids)
                    reasons.extend(other_trust.reasons)
        
        # Also consider direct trust indicators from properties
        direct_trust = entity.properties.get("direct_trust", 0.0)
        if direct_trust > 0:
            weighted_sum += direct_trust * 0.3
            total_weight += 0.3
            reasons.append(f"Direct trust: {direct_trust}")
        
        if total_weight > 0:
            trust_score = weighted_sum / total_weight
        else:
            trust_score = base_trust
        
        result = TrustScore(
            source_id=entity_id,
            target_id=entity_id,  # Self-trust
            score=min(max(trust_score, -1.0), 1.0),
            confidence=min(total_weight * 2, 1.0),
            evidence_ids=list(set(evidence_ids)),
            reasons=list(set(reasons)),
        )
        
        with self._lock:
            self._trust_cache[cache_key] = result
        
        return result
    
    def _get_cached_trust(self, entity_id: str, max_depth: int) -> TrustScore:
        """Get trust score with caching."""
        cache_key = f"{entity_id}:{max_depth}"
        if cache_key in self._trust_cache:
            return self._trust_cache[cache_key]
        return self.calculate_trust_score(entity_id, max_depth)
    
    def propagate_trust(
        self,
        source_id: str,
        initial_trust: float = 1.0,
        max_depth: int = 5,
    ) -> Dict[str, TrustScore]:
        """
        Propagate trust from a source entity to others.
        
        Args:
            source_id: The source entity to propagate trust from
            initial_trust: Initial trust value for the source
            max_depth: Maximum propagation depth
            
        Returns:
            Dictionary of entity_id -> TrustScore
        """
        # Set initial trust for source
        self._trust_cache.clear()
        
        # Recalculate trust for the source
        source_trust = self.calculate_trust_score(source_id, max_depth)
        
        # Force set the source trust
        self._trust_cache[f"{source_id}:{max_depth}"] = TrustScore(
            source_id=source_id,
            target_id=source_id,
            score=initial_trust,
            confidence=1.0,
            evidence_ids=[source_id],
            reasons=["Initial trust"],
        )
        
        # Recalculate trust for all reachable entities
        result: Dict[str, TrustScore] = {}
        entities = self.engine.list_entities()
        for entity in entities:
            try:
                trust = self.calculate_trust_score(entity.id, max_depth)
                result[entity.id] = trust
            except Exception:
                pass
        
        return result
    
    # Risk Analysis
    
    def calculate_risk_score(
        self,
        entity_id: str,
        category: str = "general",
        max_depth: int = 3,
    ) -> RiskScore:
        """
        Calculate risk score for an entity.
        
        Args:
            entity_id: The entity to calculate risk for
            category: Risk category (financial, reputation, compliance, etc.)
            max_depth: How many relationship hops to consider
            
        Returns:
            RiskScore with computed risk value
        """
        with self._lock:
            cache_key = f"{entity_id}:{category}:{max_depth}"
            if cache_key in self._risk_cache:
                return self._risk_cache[cache_key]
        
        entity = self.engine.get_entity(entity_id)
        if not entity:
            raise EntityNotFoundError(entity_id)
        
        # Base risk from entity properties
        base_risk = entity.properties.get(f"{category}_risk", 0.0)
        
        # Get risk-increasing relationships
        risk_positive = self.engine.get_relationships(
            target_id=entity_id,
            relationship_type=RelationshipType.POSITIVE_RISK,
        )
        
        # Get risk-decreasing relationships
        risk_negative = self.engine.get_relationships(
            target_id=entity_id,
            relationship_type=RelationshipType.NEGATIVE_RISK,
        )
        
        factors: Dict[str, float] = {}
        sources: List[str] = []
        
        # Process positive risk factors (increase risk)
        for rel in risk_positive:
            source_entity = self.engine.get_entity(rel.source_id)
            if source_entity:
                source_risk = self._get_cached_risk(rel.source_id, category, max_depth - 1)
                factor_value = source_risk.score * rel.weight
                factors[f"positive_{rel.source_id}"] = factor_value
                sources.append(rel.source_id)
        
        # Process negative risk factors (decrease risk)
        for rel in risk_negative:
            source_entity = self.engine.get_entity(rel.source_id)
            if source_entity:
                source_risk = self._get_cached_risk(rel.source_id, category, max_depth - 1)
                factor_value = -source_risk.score * rel.weight  # Negative contribution
                factors[f"negative_{rel.source_id}"] = factor_value
                sources.append(rel.source_id)
        
        # Combine factors
        total_positive = sum(v for v in factors.values() if v > 0)
        total_negative = sum(v for v in factors.values() if v < 0)
        
        # Calculate overall risk (0-1 scale)
        risk_score = min(max(base_risk + total_positive + total_negative, 0.0), 1.0)
        
        result = RiskScore(
            entity_id=entity_id,
            score=risk_score,
            category=category,
            confidence=min(len(factors) * 0.2, 1.0),
            sources=sources,
            factors=factors,
        )
        
        with self._lock:
            self._risk_cache[cache_key] = result
        
        return result
    
    def _get_cached_risk(self, entity_id: str, category: str, max_depth: int) -> RiskScore:
        """Get risk score with caching."""
        cache_key = f"{entity_id}:{category}:{max_depth}"
        if cache_key in self._risk_cache:
            return self._risk_cache[cache_key]
        return self.calculate_risk_score(entity_id, category, max_depth)
    
    # Supplier Analysis
    
    def get_supplier_dependencies(
        self,
        supplier_id: str,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """
        Analyze dependencies for a supplier.
        
        Args:
            supplier_id: The supplier entity ID
            max_depth: How many levels of dependencies to traverse
            
        Returns:
            Dictionary with dependency information
        """
        supplier = self.engine.get_entity(supplier_id)
        if not supplier or supplier.entity_type != EntityType.SUPPLIER:
            raise EntityNotFoundError(supplier_id)
        
        # Find all upstream dependencies (what the supplier depends on)
        upstream = self.engine.get_related_entities(
            entity_id=supplier_id,
            relationship_type=RelationshipType.DEPENDS_ON,
            max_depth=max_depth,
            direction="outgoing",
        )
        
        # Find all downstream dependencies (who depends on this supplier)
        downstream = self.engine.get_related_entities(
            entity_id=supplier_id,
            relationship_type=RelationshipType.DEPENDS_ON,
            max_depth=max_depth,
            direction="incoming",
        )
        
        # Calculate risk propagation
        upstream_risk = self._calculate_aggregate_risk(list(upstream.keys()), "financial")
        downstream_risk = self._calculate_aggregate_risk(list(downstream.keys()), "financial")
        
        return {
            "supplier_id": supplier_id,
            "supplier_name": supplier.name,
            "upstream_dependencies": list(upstream.keys()),
            "upstream_count": len(upstream),
            "downstream_dependencies": list(downstream.keys()),
            "downstream_count": len(downstream),
            "upstream_risk": upstream_risk,
            "downstream_risk": downstream_risk,
            "critical_path": self._find_critical_path(supplier_id, max_depth),
        }
    
    def _calculate_aggregate_risk(self, entity_ids: List[str], category: str) -> float:
        """Calculate aggregate risk for a list of entities."""
        if not entity_ids:
            return 0.0
        
        risks = []
        for eid in entity_ids:
            try:
                risk = self.calculate_risk_score(eid, category, max_depth=2)
                risks.append(risk.score)
            except Exception:
                pass
        
        return sum(risks) / len(risks) if risks else 0.0
    
    def _find_critical_path(
        self,
        supplier_id: str,
        max_depth: int,
    ) -> List[str]:
        """Find the most critical dependency path for a supplier."""
        # For now, just return direct dependencies
        deps = self.engine.get_related_entities(
            entity_id=supplier_id,
            relationship_type=RelationshipType.DEPENDS_ON,
            max_depth=1,
            direction="outgoing",
        )
        return list(deps.keys())
    
    # Transaction Analysis
    
    def get_connected_transactions(
        self,
        transaction_id: str,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """
        Get all transactions connected to a given transaction.
        
        Args:
            transaction_id: The transaction entity ID
            max_depth: How many levels of connections to traverse
            
        Returns:
            Dictionary with connected transactions and their relationships
        """
        transaction = self.engine.get_entity(transaction_id)
        if not transaction or transaction.entity_type != EntityType.TRANSACTION:
            raise EntityNotFoundError(transaction_id)
        
        # Find all related transactions
        related = self.engine.get_related_entities(
            entity_id=transaction_id,
            max_depth=max_depth,
        )
        
        # Filter to only transaction entities
        connected_transactions = {
            eid: (entity, rels)
            for eid, (entity, rels) in related.items()
            if entity.entity_type == EntityType.TRANSACTION
        }
        
        # Calculate risk scores
        risk_scores = {
            eid: self.calculate_risk_score(eid, "financial", max_depth=2).score
            for eid in connected_transactions
        }
        
        return {
            "transaction_id": transaction_id,
            "connected_transactions": list(connected_transactions.keys()),
            "count": len(connected_transactions),
            "risk_scores": risk_scores,
            "average_risk": sum(risk_scores.values()) / len(risk_scores) if risk_scores else 0.0,
        }
    
    # Recommendation Generation
    
    def generate_supplier_recommendations(
        self,
        user_id: str,
        requirements: Dict[str, Any],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Generate supplier recommendations based on graph relationships.
        
        Args:
            user_id: The user requesting recommendations
            requirements: User requirements (budget, category, etc.)
            limit: Maximum number of recommendations to return
            
        Returns:
            List of recommendation dictionaries
        """
        # Find user entity
        user = self.engine.get_entity(user_id)
        if not user or user.entity_type != EntityType.USER:
            raise EntityNotFoundError(user_id)
        
        # Find all suppliers
        suppliers = [
            e for e in self.engine.list_entities(EntityType.SUPPLIER)
            if e.is_active
        ]
        
        recommendations = []
        for supplier in suppliers:
            score = self._calculate_supplier_score(supplier, user, requirements)
            if score > 0:
                recommendations.append({
                    "supplier_id": supplier.id,
                    "supplier_name": supplier.name,
                    "score": score,
                    "trust_score": self.calculate_trust_score(supplier.id).score,
                    "risk_score": self.calculate_risk_score(supplier.id, "financial").score,
                    "reasons": self._get_supplier_recommendation_reasons(supplier, user, requirements),
                })
        
        # Sort by score
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        
        return recommendations[:limit]
    
    def _calculate_supplier_score(
        self,
        supplier: Entity,
        user: Entity,
        requirements: Dict[str, Any],
    ) -> float:
        """Calculate a score for a supplier based on requirements."""
        score = 0.0
        
        # Check if supplier matches category
        if "category" in requirements:
            supplier_category = supplier.properties.get("category", "")
            if supplier_category == requirements["category"]:
                score += 0.3
        
        # Check budget compatibility
        if "budget" in requirements:
            supplier_min = float(supplier.properties.get("min_price", 0))
            supplier_max = float(supplier.properties.get("max_price", float("inf")))
            budget = float(requirements["budget"])
            if supplier_min <= budget <= supplier_max:
                score += 0.3
            elif budget >= supplier_min:
                score += 0.15
        
        # Check trust score
        trust = self.calculate_trust_score(supplier.id)
        score += trust.score * 0.2
        
        # Check risk score (inverse)
        risk = self.calculate_risk_score(supplier.id, "financial")
        score += (1.0 - risk.score) * 0.15
        
        return min(score, 1.0)
    
    def _get_supplier_recommendation_reasons(
        self,
        supplier: Entity,
        user: Entity,
        requirements: Dict[str, Any],
    ) -> List[str]:
        """Generate human-readable reasons for recommendation."""
        reasons = []
        
        if "category" in requirements:
            supplier_category = supplier.properties.get("category", "")
            if supplier_category == requirements["category"]:
                reasons.append(f"Matches required category: {supplier_category}")
        
        if "budget" in requirements:
            supplier_min = float(supplier.properties.get("min_price", 0))
            supplier_max = float(supplier.properties.get("max_price", float("inf")))
            budget = float(requirements["budget"])
            if supplier_min <= budget <= supplier_max:
                reasons.append(f"Within budget range: ${supplier_min:,.2f} - ${supplier_max:,.2f}")
        
        trust = self.calculate_trust_score(supplier.id)
        if trust.score >= 0.7:
            reasons.append(f"High trust score: {trust.score:.1%}")
        
        risk = self.calculate_risk_score(supplier.id, "financial")
        if risk.score <= 0.3:
            reasons.append(f"Low financial risk: {risk.score:.1%}")
        
        return reasons
    
    # Evidence Intelligence
    
    def explain_decision(
        self,
        decision_id: str,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """
        Generate an explanation for a decision based on evidence graph.
        
        Args:
            decision_id: The decision entity ID
            max_depth: How deep to look for evidence
            
        Returns:
            Dictionary with explanation details
        """
        decision = self.engine.get_entity(decision_id)
        if not decision:
            raise EntityNotFoundError(decision_id)
        
        # Find all evidence supporting this decision
        evidence = self.engine.get_related_entities(
            entity_id=decision_id,
            relationship_type=RelationshipType.SUPPORTS,
            max_depth=max_depth,
            direction="incoming",
        )
        
        # Find all claims
        claims = self.engine.get_related_entities(
            entity_id=decision_id,
            relationship_type=RelationshipType.CITES,
            max_depth=max_depth,
            direction="incoming",
        )
        
        explanation = {
            "decision_id": decision_id,
            "decision": decision.name,
            "evidence_count": len(evidence),
            "evidence": [
                {
                    "id": eid,
                    "name": entity.name,
                    "type": entity.entity_type.value,
                    "trust_score": self.calculate_trust_score(eid).score,
                }
                for eid, (entity, _) in evidence.items()
            ],
            "claims_count": len(claims),
            "claims": [
                {
                    "id": eid,
                    "statement": entity.name,
                    "type": entity.entity_type.value,
                }
                for eid, (entity, _) in claims.items()
            ],
            "confidence": self._calculate_decision_confidence(decision_id, evidence, claims),
        }
        
        return explanation
    
    def _calculate_decision_confidence(
        self,
        decision_id: str,
        evidence: Dict[str, Any],
        claims: Dict[str, Any],
    ) -> float:
        """Calculate confidence score for a decision."""
        if not evidence:
            return 0.0
        
        total_trust = 0.0
        for eid in evidence:
            try:
                total_trust += self.calculate_trust_score(eid).score
            except Exception:
                pass
        
        return min(total_trust / len(evidence), 1.0)
    
    def clear_cache(self) -> None:
        """Clear all cached scores."""
        with self._lock:
            self._trust_cache.clear()
            self._risk_cache.clear()


def get_graph_analyzer() -> GraphAnalyzer:
    """Get the singleton graph analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = GraphAnalyzer()
    return _analyzer_instance
