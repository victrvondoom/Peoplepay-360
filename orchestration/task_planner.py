"""Task planner for agent orchestration.

Responsible for decomposing tasks, creating execution plans,
and determining optimal agent and tool selection.
"""

from __future__ import annotations

import threading
from typing import Any

from orchestration.models import (
    TaskDefinition,
    ExecutionPlan,
    AgentCapability,
)
from orchestration.agent_registry import get_agent_registry
from orchestration.errors import (
    AgentNotFoundError,
    AgentError,
)


class TaskPlanner:
    """Plans task execution by decomposing tasks and selecting agents."""
    
    def __init__(self) -> None:
        self._registry = get_agent_registry()
        self._lock = threading.RLock()
    
    def decompose_task(
        self,
        task: TaskDefinition,
    ) -> list[TaskDefinition]:
        """Decompose a task into subtasks.
        
        For complex tasks, this can break them down into smaller,
        more manageable subtasks that can be executed by different agents.
        """
        # For now, return the task as a single task
        # In the future, this can use AI or rule-based decomposition
        return [task]
    
    def plan_execution(
        self,
        task: TaskDefinition,
        workflow_id: str | None = None,
    ) -> ExecutionPlan:
        """Create an execution plan for a task.
        
        The plan includes:
        - Steps to execute
        - Agent assignments
        - Tool selections
        - Dependencies
        - Handoff points
        - Approval checkpoints
        """
        with self._lock:
            plan = ExecutionPlan(task_id=task.task_id)
            
            # Decompose task into steps
            subtasks = self.decompose_task(task)
            
            # For each subtask, select the best agent
            for subtask in subtasks:
                # Select agent based on required capabilities
                best_agent = self.select_agent(subtask.capabilities_needed)
                
                if not best_agent:
                    raise AgentError(
                        message=f"No agent available for capabilities: {subtask.capabilities_needed}",
                        code="PLANNER_001",
                        task_id=subtask.task_id,
                    )
                
                # Create step
                step = {
                    "id": subtask.task_id,
                    "name": subtask.name,
                    "description": subtask.description,
                    "agent_id": best_agent.id,
                    "agent_name": best_agent.name,
                    "capabilities": subtask.capabilities_needed,
                    "priority": subtask.priority.value,
                    "timeout": subtask.timeout_seconds,
                    "budget": subtask.budget,
                    "requires_approval": subtask.requires_approval,
                    "requires_human_input": subtask.requires_human_input,
                    "context": subtask.context,
                    "metadata": subtask.metadata,
                }
                
                step_id = plan.add_step(step)
                
                # Add approval checkpoints if needed
                if subtask.requires_approval:
                    # Get permissions from agent capabilities
                    permissions = []
                    for cap in best_agent.capabilities:
                        if cap.name in subtask.capabilities_needed:
                            permissions.extend(cap.permissions_required)
                    
                    if permissions:
                        plan.add_approval_checkpoint(permissions, step_id)
            
            # Add estimated duration and cost
            plan.estimated_duration = self._estimate_duration(plan.steps)
            plan.estimated_cost = self._estimate_cost(plan.steps)
            
            return plan
    
    def select_agent(
        self,
        capabilities: list[str],
        prefer_agent_id: str | None = None,
    ) -> Any:
        """Select the best agent for a set of capabilities.
        
        Prioritizes:
        1. Preferred agent (if specified)
        2. Agents with all capabilities
        3. Agents with most capabilities
        4. Available (not disabled) agents
        """
        with self._lock:
            # If preferred agent, check if it has the capabilities
            if prefer_agent_id:
                try:
                    agent = self._registry.get_agent(prefer_agent_id)
                    if self._has_all_capabilities(agent, capabilities):
                        return agent
                except AgentNotFoundError:
                    pass
            
            # Find all agents with the required capabilities
            agents_with_caps = self._registry.find_agents_by_capability(capabilities[0]) if capabilities else []
            
            # Filter to only agents that have ALL capabilities
            best_matches = [
                agent for agent in agents_with_caps
                if self._has_all_capabilities(agent, capabilities)
                and self._registry.check_agent_available(agent.id)
            ]
            
            if best_matches:
                # Return the first available (could add more sophisticated selection)
                return best_matches[0]
            
            # If no perfect match, try agents with most capabilities
            all_agents = self._registry.list_agents()
            scored_agents = []
            for agent in all_agents:
                if not self._registry.check_agent_available(agent.id):
                    continue
                score = self._score_agent_for_capabilities(agent, capabilities)
                if score > 0:
                    scored_agents.append((score, agent))
            
            if scored_agents:
                scored_agents.sort(key=lambda x: x[0], reverse=True)
                return scored_agents[0][1]
            
            return None
    
    def _has_all_capabilities(
        self,
        agent: Any,
        capabilities: list[str],
    ) -> bool:
        """Check if an agent has all required capabilities."""
        agent_caps = [cap.name for cap in agent.capabilities]
        return all(cap in agent_caps for cap in capabilities)
    
    def _score_agent_for_capabilities(
        self,
        agent: Any,
        capabilities: list[str],
    ) -> int:
        """Score an agent based on how many capabilities it has."""
        agent_caps = [cap.name for cap in agent.capabilities]
        return sum(1 for cap in capabilities if cap in agent_caps)
    
    def _estimate_duration(self, steps: list[dict[str, Any]]) -> float:
        """Estimate total execution duration."""
        total = 0.0
        for step in steps:
            # Use step timeout as estimate
            total += step.get("timeout", 300.0)
        return total
    
    def _estimate_cost(self, steps: list[dict[str, Any]]) -> dict[str, float]:
        """Estimate execution cost."""
        cost = {"compute_seconds": 0.0, "token_count": 0.0, "api_calls": 0.0}
        for step in steps:
            budget = step.get("budget", {})
            for key, value in budget.items():
                if key in cost:
                    cost[key] += value
        return cost
    
    def validate_task(self, task: TaskDefinition) -> list[str]:
        """Validate a task definition.
        
        Returns list of validation errors.
        """
        errors = []
        
        if not task.name:
            errors.append("Task name is required")
        
        if not task.task_id:
            errors.append("Task ID is required")
        
        # Check if required capabilities have agents available
        if task.capabilities_needed:
            for cap in task.capabilities_needed:
                agents = self._registry.find_agents_by_capability(cap)
                if not agents:
                    errors.append(f"No agent available for capability: {cap}")
        
        return errors


# Global task planner instance
_task_planner: TaskPlanner | None = None
_planner_lock = threading.Lock()


def get_task_planner() -> TaskPlanner:
    """Get the global task planner instance."""
    global _task_planner
    with _planner_lock:
        if _task_planner is None:
            _task_planner = TaskPlanner()
        return _task_planner


def reset_task_planner() -> None:
    """Reset the global task planner (for testing)."""
    global _task_planner
    with _planner_lock:
        _task_planner = TaskPlanner()
