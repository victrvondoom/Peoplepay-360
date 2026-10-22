"""Agent registry for the orchestration layer.

The registry maintains a catalog of available agents, their capabilities,
permissions, and configurations.
"""

from __future__ import annotations

import threading
from typing import Any

from orchestration.models import (
    AgentCapability,
    AgentMetadata,
    AgentRegistration,
    AgentStatus,
    AgentType,
    ToolDefinition,
)
from orchestration.errors import (
    AgentNotFoundError,
    AgentRegistrationError,
    AgentDisabledError,
)


class AgentRegistry:
    """Registry of available agents.
    
    Thread-safe registry that maintains agent metadata, capabilities,
    and tool definitions.
    """
    
    def __init__(self) -> None:
        self._agents: dict[str, AgentMetadata] = {}
        self._tools: dict[str, ToolDefinition] = {}
        self._agent_tools: dict[str, list[str]] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._lock = threading.RLock()
    
    def register_agent(self, registration: AgentRegistration) -> AgentMetadata:
        """Register a new agent."""
        with self._lock:
            if registration.agent_id in self._agents:
                raise AgentRegistrationError(
                    f"Agent {registration.agent_id} already registered",
                    agent_id=registration.agent_id,
                )
            
            metadata = AgentMetadata(
                id=registration.agent_id,
                name=registration.name,
                description=registration.description,
                version=registration.version,
                agent_type=registration.agent_type,
                status=registration.status,
                capabilities=registration.capabilities,
                tags=registration.tags,
            )
            
            self._agents[registration.agent_id] = metadata
            
            # Index capabilities
            for cap in registration.capabilities:
                if cap.name not in self._capability_index:
                    self._capability_index[cap.name] = []
                if registration.agent_id not in self._capability_index[cap.name]:
                    self._capability_index[cap.name].append(registration.agent_id)
            
            # Register tools
            for cap in registration.capabilities:
                for tool_name in cap.tool_names:
                    self._register_tool_from_capability(tool_name, cap, registration.agent_id)
            
            return metadata
    
    def _register_tool_from_capability(
        self, tool_name: str, cap: AgentCapability, agent_id: str
    ) -> None:
        """Register a tool from an agent capability."""
        if tool_name not in self._tools:
            # Create a basic tool definition from the capability
            self._tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=f"Tool from {cap.name} capability",
                permissions_required=cap.permissions_required,
                timeout_seconds=cap.timeout_seconds,
                max_retries=cap.max_retries,
                requires_approval=cap.requires_approval,
            )
        
        # Map agent to tool
        if agent_id not in self._agent_tools:
            self._agent_tools[agent_id] = []
        if tool_name not in self._agent_tools[agent_id]:
            self._agent_tools[agent_id].append(tool_name)
    
    def register_tool(self, tool: ToolDefinition, agent_id: str | None = None) -> None:
        """Register a tool."""
        with self._lock:
            self._tools[tool.name] = tool
            if agent_id:
                if agent_id not in self._agent_tools:
                    self._agent_tools[agent_id] = []
                if tool.name not in self._agent_tools[agent_id]:
                    self._agent_tools[agent_id].append(tool.name)
    
    def get_agent(self, agent_id: str) -> AgentMetadata:
        """Get agent metadata by ID."""
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(agent_id)
            return self._agents[agent_id]
    
    def get_tool(self, tool_name: str) -> ToolDefinition:
        """Get tool definition by name."""
        with self._lock:
            if tool_name not in self._tools:
                raise KeyError(f"Tool not found: {tool_name}")
            return self._tools[tool_name]
    
    def list_agents(
        self,
        agent_type: AgentType | None = None,
        status: AgentStatus | None = None,
        capability: str | None = None,
        tag: str | None = None,
    ) -> list[AgentMetadata]:
        """List agents with optional filters."""
        with self._lock:
            agents = list(self._agents.values())
            
            if agent_type:
                agents = [a for a in agents if a.agent_type == agent_type]
            
            if status:
                agents = [a for a in agents if a.status == status]
            
            if capability:
                agent_ids_with_cap = self._capability_index.get(capability, [])
                agents = [a for a in agents if a.id in agent_ids_with_cap]
            
            if tag:
                agents = [a for a in agents if tag in a.tags]
            
            return agents
    
    def list_tools(self, agent_id: str | None = None) -> list[ToolDefinition]:
        """List tools, optionally filtered by agent."""
        with self._lock:
            if agent_id:
                if agent_id not in self._agent_tools:
                    return []
                tool_names = self._agent_tools[agent_id]
                return [self._tools[name] for name in tool_names if name in self._tools]
            return list(self._tools.values())
    
    def find_agents_by_capability(self, capability_name: str) -> list[AgentMetadata]:
        """Find agents that have a specific capability."""
        with self._lock:
            agent_ids = self._capability_index.get(capability_name, [])
            return [self._agents[aid] for aid in agent_ids if aid in self._agents]
    
    def enable_agent(self, agent_id: str) -> AgentMetadata:
        """Enable an agent."""
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(agent_id)
            self._agents[agent_id].status = AgentStatus.ACTIVE
            self._agents[agent_id].disabled_reason = None
            self._agents[agent_id].updated_at = self._agents[agent_id].updated_at.replace(microsecond=0)
            return self._agents[agent_id]
    
    def disable_agent(self, agent_id: str, reason: str | None = None) -> AgentMetadata:
        """Disable an agent."""
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(agent_id)
            self._agents[agent_id].status = AgentStatus.DISABLED
            self._agents[agent_id].disabled_reason = reason
            self._agents[agent_id].updated_at = self._agents[agent_id].updated_at.replace(microsecond=0)
            return self._agents[agent_id]
    
    def check_agent_available(self, agent_id: str) -> bool:
        """Check if an agent is available (enabled and not paused)."""
        with self._lock:
            if agent_id not in self._agents:
                return False
            agent = self._agents[agent_id]
            return agent.status == AgentStatus.ACTIVE
    
    def get_agent_capabilities(self, agent_id: str) -> list[AgentCapability]:
        """Get capabilities for an agent."""
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(agent_id)
            return self._agents[agent_id].capabilities
    
    def has_capability(self, agent_id: str, capability_name: str) -> bool:
        """Check if an agent has a specific capability."""
        with self._lock:
            if agent_id not in self._agents:
                return False
            return any(cap.name == capability_name for cap in self._agents[agent_id].capabilities)
    
    def has_tool(self, agent_id: str, tool_name: str) -> bool:
        """Check if an agent has access to a specific tool."""
        with self._lock:
            if agent_id not in self._agent_tools:
                return False
            return tool_name in self._agent_tools[agent_id]


# Global registry instance
_agent_registry: AgentRegistry | None = None
_registry_lock = threading.Lock()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    global _agent_registry
    with _registry_lock:
        if _agent_registry is None:
            _agent_registry = AgentRegistry()
        return _agent_registry


def reset_agent_registry() -> None:
    """Reset the global agent registry (for testing)."""
    global _agent_registry
    with _registry_lock:
        _agent_registry = AgentRegistry()
