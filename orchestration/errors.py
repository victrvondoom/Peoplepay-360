"""Agent orchestration error types."""

from typing import Any


class AgentError(Exception):
    """Base class for agent orchestration errors."""
    
    def __init__(
        self,
        message: str,
        code: str = "AGENT_000",
        agent_id: str | None = None,
        task_id: str | None = None,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.agent_id = agent_id
        self.task_id = task_id
        self.details = details or {}
        self.cause = cause
        
        if agent_id:
            self.details["agent_id"] = agent_id
        if task_id:
            self.details["task_id"] = task_id
        
        super().__init__(message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for API responses."""
        result = {
            "error": self.message,
            "code": self.code,
            "type": self.__class__.__name__,
        }
        if self.details:
            result["details"] = self.details
        return result


class AgentNotFoundError(AgentError):
    """Agent not found in registry."""
    
    def __init__(self, agent_id: str) -> None:
        super().__init__(
            message=f"Agent not found: {agent_id}",
            code="AGENT_001",
            agent_id=agent_id,
        )


class AgentRegistrationError(AgentError):
    """Failed to register agent."""
    
    def __init__(self, message: str, agent_id: str | None = None, cause: Exception | None = None) -> None:
        super().__init__(
            message=message,
            code="AGENT_002",
            agent_id=agent_id,
            cause=cause,
        )


class AgentDisabledError(AgentError):
    """Agent is disabled."""
    
    def __init__(self, agent_id: str, reason: str | None = None) -> None:
        message = f"Agent disabled: {agent_id}"
        if reason:
            message += f" - {reason}"
        super().__init__(
            message=message,
            code="AGENT_003",
            agent_id=agent_id,
            details={"reason": reason} if reason else None,
        )


class TaskTimeoutError(AgentError):
    """Task execution timed out."""
    
    def __init__(self, task_id: str, timeout_seconds: float, agent_id: str | None = None) -> None:
        super().__init__(
            message=f"Task {task_id} timed out after {timeout_seconds}s",
            code="AGENT_100",
            task_id=task_id,
            agent_id=agent_id,
            details={"timeout_seconds": timeout_seconds},
        )
        self.timeout_seconds = timeout_seconds


class TaskCancelledError(AgentError):
    """Task was cancelled."""
    
    def __init__(self, task_id: str, reason: str | None = None, agent_id: str | None = None) -> None:
        message = f"Task cancelled: {task_id}"
        if reason:
            message += f" - {reason}"
        super().__init__(
            message=message,
            code="AGENT_101",
            task_id=task_id,
            agent_id=agent_id,
            details={"reason": reason} if reason else None,
        )
        self.reason = reason


class MaxRetriesExceededError(AgentError):
    """Maximum retries exceeded for task."""
    
    def __init__(self, task_id: str, max_retries: int, attempt_count: int, agent_id: str | None = None) -> None:
        super().__init__(
            message=f"Task {task_id} failed after {attempt_count}/{max_retries} retries",
            code="AGENT_102",
            task_id=task_id,
            agent_id=agent_id,
            details={"max_retries": max_retries, "attempt_count": attempt_count},
        )
        self.max_retries = max_retries
        self.attempt_count = attempt_count


class ConcurrencyLimitError(AgentError):
    """Concurrency limit exceeded."""
    
    def __init__(self, agent_id: str, current: int, limit: int) -> None:
        super().__init__(
            message=f"Agent {agent_id} concurrency limit exceeded: {current}/{limit}",
            code="AGENT_103",
            agent_id=agent_id,
            details={"current": current, "limit": limit},
        )
        self.current = current
        self.limit = limit


class BudgetExceededError(AgentError):
    """Task budget exceeded."""
    
    def __init__(self, task_id: str, budget_type: str, used: float, limit: float, agent_id: str | None = None) -> None:
        super().__init__(
            message=f"Task {task_id} {budget_type} budget exceeded: {used}/{limit}",
            code="AGENT_104",
            task_id=task_id,
            agent_id=agent_id,
            details={"budget_type": budget_type, "used": used, "limit": limit},
        )
        self.budget_type = budget_type
        self.used = used
        self.limit = limit


class ApprovalRequiredError(AgentError):
    """Human approval required for task."""
    
    def __init__(
        self,
        task_id: str,
        reason: str,
        required_permissions: list[str] | None = None,
        agent_id: str | None = None,
    ) -> None:
        super().__init__(
            message=f"Approval required for task {task_id}: {reason}",
            code="AGENT_200",
            task_id=task_id,
            agent_id=agent_id,
            details={"reason": reason, "required_permissions": required_permissions},
        )
        self.reason = reason
        self.required_permissions = required_permissions or []


class ToolNotFoundError(AgentError):
    """Tool not found."""
    
    def __init__(self, tool_name: str, agent_id: str | None = None) -> None:
        super().__init__(
            message=f"Tool not found: {tool_name}",
            code="AGENT_300",
            agent_id=agent_id,
            details={"tool_name": tool_name},
        )
        self.tool_name = tool_name


class ToolExecutionError(AgentError):
    """Tool execution failed."""
    
    def __init__(
        self,
        tool_name: str,
        message: str,
        agent_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message=f"Tool {tool_name} execution failed: {message}",
            code="AGENT_301",
            agent_id=agent_id,
            details={"tool_name": tool_name},
            cause=cause,
        )
        self.tool_name = tool_name


class HandoffError(AgentError):
    """Agent-to-agent handoff failed."""
    
    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        reason: str,
        task_id: str | None = None,
    ) -> None:
        super().__init__(
            message=f"Handoff from {from_agent} to {to_agent} failed: {reason}",
            code="AGENT_400",
            agent_id=from_agent,
            task_id=task_id,
            details={"from_agent": from_agent, "to_agent": to_agent, "reason": reason},
        )
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.reason = reason
