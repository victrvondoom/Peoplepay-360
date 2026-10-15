"""Data models for agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class AgentStatus(str, Enum):
    """Agent status."""
    ACTIVE = "active"
    DISABLED = "disabled"
    PAUSED = "paused"
    ERROR = "error"


class AgentType(str, Enum):
    """Agent type."""
    SYSTEM = "system"
    DOMAIN = "domain"
    WORKFLOW = "workflow"
    TOOL = "tool"
    ASSISTANT = "assistant"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"


class Priority(str, Enum):
    """Task priority."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentCapability:
    """An agent's capability."""
    name: str
    description: str
    tool_names: list[str] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    requires_approval: bool = False
    timeout_seconds: float = 300.0
    max_retries: int = 3
    concurrency_limit: int = 1
    budget: dict[str, float] = field(default_factory=dict)


@dataclass
class AgentMetadata:
    """Agent metadata."""
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    agent_type: AgentType = AgentType.DOMAIN
    status: AgentStatus = AgentStatus.ACTIVE
    capabilities: list[AgentCapability] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    disabled_reason: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ToolDefinition:
    """Tool definition."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required_parameters: list[str] = field(default_factory=list)
    returns: str = "any"
    permissions_required: list[str] = field(default_factory=list)
    timeout_seconds: float = 60.0
    max_retries: int = 3
    requires_approval: bool = False


@dataclass
class TaskDefinition:
    """Task definition."""
    name: str
    task_id: str = field(default_factory=lambda: f"task-{uuid4().hex}")
    description: str | None = None
    agent_id: str | None = None
    capabilities_needed: list[str] = field(default_factory=list)
    priority: Priority = Priority.NORMAL
    timeout_seconds: float = 300.0
    max_retries: int = 3
    budget: dict[str, float] = field(default_factory=dict)
    requires_approval: bool = False
    requires_human_input: bool = False
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskExecution:
    """Task execution record."""
    task_id: str
    agent_id: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int = 0
    last_error: str | None = None
    result: dict[str, Any] | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    memory_snapshot: dict[str, Any] = field(default_factory=dict)
    budget_usage: dict[str, float] = field(default_factory=dict)
    approval_requests: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkflowContext:
    """Shared workflow context across agents."""
    workflow_id: str = field(default_factory=lambda: f"workflow-{uuid4().hex}")
    user_id: str | None = None
    organization_id: str | None = None
    conversation_id: str | None = None
    shared_memory: dict[str, Any] = field(default_factory=dict)
    task_history: list[str] = field(default_factory=list)
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    evidence_links: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_decision(self, decision: dict[str, Any]) -> None:
        """Add a decision to the log."""
        decision["timestamp"] = datetime.utcnow().isoformat()
        self.decision_log.append(decision)
        self.updated_at = datetime.utcnow()
    
    def add_evidence(self, evidence_id: str) -> None:
        """Add evidence link."""
        if evidence_id not in self.evidence_links:
            self.evidence_links.append(evidence_id)
        self.updated_at = datetime.utcnow()


@dataclass
class ExecutionPlan:
    """Execution plan for a task."""
    task_id: str
    plan_id: str = field(default_factory=lambda: f"plan-{uuid4().hex}")
    steps: list[dict[str, Any]] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    parallel_steps: list[list[str]] = field(default_factory=list)
    handoff_points: list[dict[str, Any]] = field(default_factory=list)
    approval_checkpoints: list[dict[str, Any]] = field(default_factory=list)
    estimated_duration: float = 0.0
    estimated_cost: dict[str, float] = field(default_factory=dict)
    
    def add_step(self, step: dict[str, Any], dependencies: list[str] | None = None) -> str:
        """Add a step to the plan."""
        step_id = step.get("id") or f"step-{uuid4().hex}"
        step["id"] = step_id
        self.steps.append(step)
        if dependencies:
            self.dependencies[step_id] = dependencies
        return step_id
    
    def add_handoff(self, from_agent: str, to_agent: str, condition: str, step_id: str) -> None:
        """Add a handoff point."""
        self.handoff_points.append({
            "from_agent": from_agent,
            "to_agent": to_agent,
            "condition": condition,
            "step_id": step_id,
        })
    
    def add_approval_checkpoint(self, required_permissions: list[str], step_id: str) -> None:
        """Add an approval checkpoint."""
        self.approval_checkpoints.append({
            "required_permissions": required_permissions,
            "step_id": step_id,
        })


@dataclass
class AgentRegistration:
    """Agent registration request."""
    agent_id: str
    name: str
    description: str
    capabilities: list[AgentCapability] = field(default_factory=list)
    agent_type: AgentType = AgentType.DOMAIN
    status: AgentStatus = AgentStatus.ACTIVE
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    configuration: dict[str, Any] = field(default_factory=dict)
