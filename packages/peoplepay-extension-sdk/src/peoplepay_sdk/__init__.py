"""Stable, bounded contracts for PeoplePay capability providers."""

from .contracts import (
    API_VERSION,
    ActionProposal,
    Capability,
    Entity,
    Evidence,
    Extension,
    ExtensionContext,
    ExtensionHealth,
    ExtensionMetadata,
    ExtensionRequest,
    ExtensionResult,
    PeoplePayEvent,
    ProviderRegistry,
)

__all__ = [
    "API_VERSION", "ActionProposal", "Capability", "Entity", "Evidence",
    "Extension", "ExtensionContext", "ExtensionHealth", "ExtensionMetadata",
    "ExtensionRequest", "ExtensionResult", "PeoplePayEvent", "ProviderRegistry",
]
