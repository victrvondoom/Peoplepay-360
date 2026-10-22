"""PeoplePay 360 - Shared Agent Orchestration Layer.

This module provides a centralized system for coordinating specialized capabilities
through agents, replacing duplicated logic across different agent implementations.

The orchestration layer supports:
- Agent registry and discovery
- Task decomposition and execution planning
- Tool selection and invocation
- Agent-to-agent handoffs
- Shared workflow context
- Scoped memory and task history
- Execution budgets and timeouts
- Retry and cancellation
- Concurrency controls
- Human approval checkpoints
- Recovery from failed tasks
- Durable task states
- Explainable decision records

All agents must request actions through the permission and workflow systems.
Agents can recommend, evaluate, and prepare actions, but cannot independently
authorize payments, bypass organization policy, or grant themselves permissions.
"""

from orchestration.agent_registry import AgentRegistry, get_agent_registry
from orchestration.task_planner import TaskPlanner, get_task_planner
from orchestration.executor import AgentExecutor, get_executor
from orchestration.context import WorkflowContext
from orchestration.memory import AgentMemory
from orchestration.errors import (
    AgentNotFoundError,
    AgentError,
    TaskTimeoutError,
    TaskCancelledError,
    ApprovalRequiredError,
    MaxRetriesExceededError,
    ConcurrencyLimitError,
    BudgetExceededError,
)

__all__ = [
    "AgentRegistry",
    "get_agent_registry",
    "TaskPlanner",
    "get_task_planner",
    "AgentExecutor",
    "get_executor",
    "WorkflowContext",
    "AgentMemory",
    "AgentNotFoundError",
    "AgentError",
    "TaskTimeoutError",
    "TaskCancelledError",
    "ApprovalRequiredError",
    "MaxRetriesExceededError",
    "ConcurrencyLimitError",
    "BudgetExceededError",
]
