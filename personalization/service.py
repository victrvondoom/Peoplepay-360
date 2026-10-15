"""
Personalization Service - Main Service
"""

import logging
from typing import Optional, List, Dict, Any
from uuid import uuid4
from datetime import datetime

from personalization.models import (
    UserPreference,
    OrganizationPreference,
    Recommendation,
    PreferenceType,
    RecommendationType,
)

logger = logging.getLogger(__name__)


class PersonalizationService:
    def __init__(self):
        self._user_preferences: Dict[str, List[UserPreference]] = {}
        self._org_preferences: Dict[str, List[OrganizationPreference]] = {}
        self._recommendations: Dict[str, Recommendation] = {}
        logger.info("PersonalizationService initialized")

    def set_user_preference(
        self,
        user_id: str,
        preference_type: PreferenceType,
        value: Any,
        priority: int = 1,
    ) -> UserPreference:
        pref = UserPreference(
            user_id=user_id,
            preference_type=preference_type,
            value=value,
            priority=priority,
        )
        if user_id not in self._user_preferences:
            self._user_preferences[user_id] = []
        self._user_preferences[user_id].append(pref)
        return pref

    def get_user_preference(
        self,
        user_id: str,
        preference_type: PreferenceType,
    ) -> Optional[UserPreference]:
        if user_id not in self._user_preferences:
            return None
        for pref in self._user_preferences[user_id]:
            if pref.preference_type == preference_type:
                return pref
        return None

    def get_all_user_preferences(self, user_id: str) -> List[UserPreference]:
        return self._user_preferences.get(user_id, [])

    def set_organization_preference(
        self,
        organization_id: str,
        preference_type: PreferenceType,
        value: Any,
        applies_to_all: bool = True,
    ) -> OrganizationPreference:
        pref = OrganizationPreference(
            organization_id=organization_id,
            preference_type=preference_type,
            value=value,
            applies_to_all=applies_to_all,
        )
        if organization_id not in self._org_preferences:
            self._org_preferences[organization_id] = []
        self._org_preferences[organization_id].append(pref)
        return pref

    def get_organization_preference(
        self,
        organization_id: str,
        preference_type: PreferenceType,
    ) -> Optional[OrganizationPreference]:
        if organization_id not in self._org_preferences:
            return None
        for pref in self._org_preferences[organization_id]:
            if pref.preference_type == preference_type:
                return pref
        return None

    def get_effective_preference(
        self,
        user_id: str,
        organization_id: Optional[str],
        preference_type: PreferenceType,
    ) -> Optional[UserPreference]:
        # User preference takes precedence
        user_pref = self.get_user_preference(user_id, preference_type)
        if user_pref:
            return user_pref
        
        # Then organization preference
        if organization_id:
            org_pref = self.get_organization_preference(organization_id, preference_type)
            if org_pref and org_pref.applies_to_all:
                # Convert to UserPreference for consistency
                return UserPreference(
                    user_id=user_id,
                    preference_type=preference_type,
                    value=org_pref.value,
                    priority=org_pref.priority if hasattr(org_pref, 'priority') else 1,
                )
        
        return None

    def create_recommendation(
        self,
        user_id: Optional[str],
        organization_id: Optional[str],
        recommendation_type: RecommendationType,
        items: List[str],
        explanation: str,
        score: float = 0.0,
        confidence: float = 0.0,
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> Recommendation:
        rec = Recommendation(
            user_id=user_id,
            organization_id=organization_id,
            recommendation_type=recommendation_type,
            items=items,
            explanation=explanation,
            score=score,
            confidence=confidence,
            evidence=evidence or [],
        )
        self._recommendations[rec.recommendation_id] = rec
        return rec

    def get_recommendation(self, recommendation_id: str) -> Optional[Recommendation]:
        return self._recommendations.get(recommendation_id)

    def list_recommendations(
        self,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> List[Recommendation]:
        recs = list(self._recommendations.values())
        if user_id:
            recs = [r for r in recs if r.user_id == user_id]
        if organization_id:
            recs = [r for r in recs if r.organization_id == organization_id]
        return recs

    def clear_user_preferences(self, user_id: str) -> int:
        count = len(self._user_preferences.get(user_id, []))
        self._user_preferences[user_id] = []
        return count


_personalization_service: Optional[PersonalizationService] = None


def get_personalization_service() -> PersonalizationService:
    global _personalization_service
    if _personalization_service is None:
        _personalization_service = PersonalizationService()
    return _personalization_service
