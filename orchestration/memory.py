"""Agent memory management for orchestration.

Provides scoped memory management for agents, allowing them to:
- Store and retrieve context-specific information
- Maintain conversation history
- Share state between related tasks
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class MemoryEntry:
    """A single memory entry."""
    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int | None = None  # Time-to-live in seconds
    scope: str = "workflow"  # workflow, task, agent, global
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if this memory entry has expired."""
        if self.ttl_seconds is None:
            return False
        expiry = self.created_at.timestamp() + self.ttl_seconds
        return datetime.utcnow().timestamp() > expiry


@dataclass
class AgentMemory:
    """Scoped memory for an agent.
    
    Memory is organized by scope and can have TTL (time-to-live) for
    automatic expiration.
    """
    memory_id: str = field(default_factory=lambda: f"memory-{uuid4().hex}")
    workflow_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    entries: dict[str, MemoryEntry] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def set(
        self,
        key: str,
        value: Any,
        scope: str = "task",
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a value in memory."""
        entry = MemoryEntry(
            key=key,
            value=value,
            ttl_seconds=ttl_seconds,
            scope=scope,
            metadata=metadata or {},
        )
        self.entries[key] = entry
        self.updated_at = datetime.utcnow()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from memory."""
        if key not in self.entries:
            return default
        entry = self.entries[key]
        if entry.is_expired():
            del self.entries[key]
            return default
        return entry.value
    
    def get_entry(self, key: str) -> MemoryEntry | None:
        """Get a memory entry by key."""
        if key not in self.entries:
            return None
        entry = self.entries[key]
        if entry.is_expired():
            del self.entries[key]
            return None
        return entry
    
    def delete(self, key: str) -> bool:
        """Delete a memory entry."""
        if key in self.entries:
            del self.entries[key]
            self.updated_at = datetime.utcnow()
            return True
        return False
    
    def clear(self) -> None:
        """Clear all memory entries."""
        self.entries.clear()
        self.updated_at = datetime.utcnow()
    
    def clear_expired(self) -> int:
        """Remove expired entries and return count."""
        expired_keys = [key for key, entry in self.entries.items() if entry.is_expired()]
        for key in expired_keys:
            del self.entries[key]
        if expired_keys:
            self.updated_at = datetime.utcnow()
        return len(expired_keys)
    
    def get_all(self, scope: str | None = None) -> dict[str, Any]:
        """Get all memory entries, optionally filtered by scope."""
        result = {}
        for key, entry in self.entries.items():
            if entry.is_expired():
                continue
            if scope is None or entry.scope == scope:
                result[key] = entry.value
        return result
    
    def to_dict(self) -> dict[str, Any]:
        """Convert memory to dictionary for serialization."""
        return {
            "memory_id": self.memory_id,
            "workflow_id": self.workflow_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "entries": {
                key: {
                    "value": entry.value,
                    "created_at": entry.created_at.isoformat(),
                    "updated_at": entry.updated_at.isoformat(),
                    "ttl_seconds": entry.ttl_seconds,
                    "scope": entry.scope,
                    "metadata": entry.metadata,
                }
                for key, entry in self.entries.items()
                if not entry.is_expired()
            },
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class MemoryManager:
    """Manages agent memory across workflows."""
    
    def __init__(self) -> None:
        self._memories: dict[str, AgentMemory] = {}
        self._lock = threading.RLock()
    
    def get_memory(
        self,
        workflow_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> AgentMemory:
        """Get or create memory for a specific scope."""
        with self._lock:
            memory_id = self._generate_memory_id(workflow_id, agent_id, task_id)
            if memory_id not in self._memories:
                self._memories[memory_id] = AgentMemory(
                    memory_id=memory_id,
                    workflow_id=workflow_id,
                    agent_id=agent_id,
                    task_id=task_id,
                )
            return self._memories[memory_id]
    
    def _generate_memory_id(
        self,
        workflow_id: str | None,
        agent_id: str | None,
        task_id: str | None,
    ) -> str:
        """Generate a unique memory ID for a scope."""
        parts = []
        if workflow_id:
            parts.append(workflow_id)
        if agent_id:
            parts.append(agent_id)
        if task_id:
            parts.append(task_id)
        return "|".join(parts) if parts else f"global-{uuid4().hex}"
    
    def delete_memory(
        self,
        workflow_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> bool:
        """Delete memory for a specific scope."""
        with self._lock:
            memory_id = self._generate_memory_id(workflow_id, agent_id, task_id)
            if memory_id in self._memories:
                del self._memories[memory_id]
                return True
            return False
    
    def clear_all_expired(self) -> int:
        """Clear all expired memory entries across all scopes."""
        with self._lock:
            total_cleared = 0
            for memory in self._memories.values():
                total_cleared += memory.clear_expired()
            return total_cleared
    
    def get_memory_by_id(self, memory_id: str) -> AgentMemory | None:
        """Get memory by its ID."""
        with self._lock:
            return self._memories.get(memory_id)


# Global memory manager instance
_memory_manager: MemoryManager | None = None
_memory_lock = threading.Lock()


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance."""
    global _memory_manager
    with _memory_lock:
        if _memory_manager is None:
            _memory_manager = MemoryManager()
        return _memory_manager


def reset_memory_manager() -> None:
    """Reset the global memory manager (for testing)."""
    global _memory_manager
    with _memory_lock:
        _memory_manager = MemoryManager()
