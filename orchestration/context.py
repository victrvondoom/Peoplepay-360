"""Workflow context management for agent orchestration.

Provides shared context, memory, and state management across agents
in a workflow.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any
from uuid import uuid4

from orchestration.models import WorkflowContext
from orchestration.errors import AgentError


class ContextManager:
    """Manages workflow contexts for agent orchestration."""
    
    def __init__(self) -> None:
        self._contexts: dict[str, WorkflowContext] = {}
        self._lock = threading.RLock()
    
    def create_context(
        self,
        user_id: str | None = None,
        organization_id: str | None = None,
        conversation_id: str | None = None,
        workflow_id: str | None = None,
        initial_memory: dict[str, Any] | None = None,
    ) -> WorkflowContext:
        """Create a new workflow context."""
        with self._lock:
            workflow_id = workflow_id or f"workflow-{uuid4().hex}"
            context = WorkflowContext(
                workflow_id=workflow_id,
                user_id=user_id,
                organization_id=organization_id,
                conversation_id=conversation_id,
                shared_memory=initial_memory or {},
            )
            self._contexts[workflow_id] = context
            return context
    
    def get_context(self, workflow_id: str) -> WorkflowContext:
        """Get a workflow context by ID."""
        with self._lock:
            if workflow_id not in self._contexts:
                raise AgentError(
                    message=f"Workflow context not found: {workflow_id}",
                    code="CONTEXT_001",
                )
            return self._contexts[workflow_id]
    
    def update_context(
        self,
        workflow_id: str,
        updates: dict[str, Any],
    ) -> WorkflowContext:
        """Update a workflow context."""
        with self._lock:
            if workflow_id not in self._contexts:
                raise AgentError(
                    message=f"Workflow context not found: {workflow_id}",
                    code="CONTEXT_001",
                )
            context = self._contexts[workflow_id]
            
            if "shared_memory" in updates:
                context.shared_memory.update(updates["shared_memory"])
            
            if "evidence_links" in updates:
                for link in updates["evidence_links"]:
                    context.add_evidence(link)
            
            context.updated_at = datetime.utcnow()
            return context
    
    def delete_context(self, workflow_id: str) -> None:
        """Delete a workflow context."""
        with self._lock:
            if workflow_id in self._contexts:
                del self._contexts[workflow_id]
    
    def add_decision(
        self,
        workflow_id: str,
        decision: dict[str, Any],
    ) -> None:
        """Add a decision to a workflow context."""
        with self._lock:
            if workflow_id not in self._contexts:
                raise AgentError(
                    message=f"Workflow context not found: {workflow_id}",
                    code="CONTEXT_001",
                )
            self._contexts[workflow_id].add_decision(decision)
    
    def add_evidence_link(
        self,
        workflow_id: str,
        evidence_id: str,
    ) -> None:
        """Add an evidence link to a workflow context."""
        with self._lock:
            if workflow_id not in self._contexts:
                raise AgentError(
                    message=f"Workflow context not found: {workflow_id}",
                    code="CONTEXT_001",
                )
            self._contexts[workflow_id].add_evidence(evidence_id)
    
    def list_contexts(
        self,
        user_id: str | None = None,
        organization_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkflowContext]:
        """List workflow contexts with optional filters."""
        with self._lock:
            contexts = list(self._contexts.values())
            
            if user_id:
                contexts = [c for c in contexts if c.user_id == user_id]
            
            if organization_id:
                contexts = [c for c in contexts if c.organization_id == organization_id]
            
            # Sort by updated_at descending
            contexts.sort(key=lambda c: c.updated_at, reverse=True)
            
            return contexts[offset:offset + limit]
    
    def get_task_history(self, workflow_id: str) -> list[str]:
        """Get task history for a workflow."""
        with self._lock:
            if workflow_id not in self._contexts:
                raise AgentError(
                    message=f"Workflow context not found: {workflow_id}",
                    code="CONTEXT_001",
                )
            return self._contexts[workflow_id].task_history
    
    def get_decision_log(self, workflow_id: str) -> list[dict[str, Any]]:
        """Get decision log for a workflow."""
        with self._lock:
            if workflow_id not in self._contexts:
                raise AgentError(
                    message=f"Workflow context not found: {workflow_id}",
                    code="CONTEXT_001",
                )
            return self._contexts[workflow_id].decision_log


# Global context manager instance
_context_manager: ContextManager | None = None
_context_lock = threading.Lock()


def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    global _context_manager
    with _context_lock:
        if _context_manager is None:
            _context_manager = ContextManager()
        return _context_manager


def reset_context_manager() -> None:
    """Reset the global context manager (for testing)."""
    global _context_manager
    with _context_lock:
        _context_manager = ContextManager()
