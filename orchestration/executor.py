"""Agent executor for orchestration.

Executes tasks by invoking agents, managing their lifecycle,
handling retries, timeouts, and approvals.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from queue import Queue
from uuid import uuid4

from orchestration.models import (
    TaskDefinition,
    TaskStatus,
    TaskExecution,
    ExecutionPlan,
    Priority,
)
from orchestration.agent_registry import get_agent_registry
from orchestration.context import get_context_manager
from orchestration.memory import get_memory_manager
from orchestration.errors import (
    AgentNotFoundError,
    AgentError,
    TaskTimeoutError,
    TaskCancelledError,
    MaxRetriesExceededError,
    ConcurrencyLimitError,
    BudgetExceededError,
    ApprovalRequiredError,
)


@dataclass
class ExecutionResult:
    """Result of a task execution."""
    task_id: str
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    attempt_count: int = 0
    duration_seconds: float = 0.0
    decisions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    budget_usage: dict[str, float] = field(default_factory=dict)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    approval_requests: list[dict[str, Any]] = field(default_factory=list)


class AgentExecutor:
    """Executes tasks using agents.
    
    Manages:
    - Task lifecycle (pending, running, completed, failed, cancelled)
    - Retries with exponential backoff
    - Timeouts
    - Concurrency limits per agent
    - Budget tracking
    - Human approval checkpoints
    - Agent-to-agent handoffs
    """
    
    def __init__(
        self,
        max_concurrent_tasks: int = 10,
        max_retries: int = 3,
        default_timeout: float = 300.0,
    ) -> None:
        self._registry = get_agent_registry()
        self._context_manager = get_context_manager()
        self._memory_manager = get_memory_manager()
        
        self._max_concurrent_tasks = max_concurrent_tasks
        self._max_retries = max_retries
        self._default_timeout = default_timeout
        
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_tasks)
        self._task_queue = Queue()
        self._running_tasks: dict[str, Future] = {}
        self._task_states: dict[str, TaskExecution] = {}
        self._agent_concurrency: dict[str, int] = {}
        self._lock = threading.RLock()
        self._shutdown = False
    
    def execute(
        self,
        task: TaskDefinition,
        plan: ExecutionPlan | None = None,
        workflow_id: str | None = None,
        approval_callback: Callable[[dict[str, Any]], bool] | None = None,
        handoff_callback: Callable[[dict[str, Any]], bool] | None = None,
    ) -> ExecutionResult:
        """Execute a task with an agent.
        
        This is the main entry point for task execution.
        """
        with self._lock:
            if self._shutdown:
                raise AgentError("Executor is shutting down", code="EXECUTOR_001")
            
            # Create execution record
            execution = TaskExecution(
                task_id=task.task_id,
                agent_id=task.agent_id or "",
                status=TaskStatus.PENDING,
            )
            self._task_states[task.task_id] = execution
            
            # Create context if workflow_id provided
            if workflow_id:
                context = self._context_manager.get_context(workflow_id)
            else:
                context = None
            
            # Get memory for this task
            memory = self._memory_manager.get_memory(
                workflow_id=workflow_id,
                agent_id=task.agent_id,
                task_id=task.task_id,
            )
        
        # Submit to thread pool
        future = self._executor.submit(
            self._execute_task,
            task=task,
            plan=plan,
            workflow_id=workflow_id,
            context=context,
            memory=memory,
            approval_callback=approval_callback,
            handoff_callback=handoff_callback,
        )
        
        with self._lock:
            self._running_tasks[task.task_id] = future
        
        # Wait for completion and get result
        try:
            result = future.result(timeout=task.timeout_seconds or self._default_timeout)
            return result
        except asyncio.TimeoutError:
            with self._lock:
                if task.task_id in self._running_tasks:
                    self._running_tasks[task.task_id].cancel()
                    del self._running_tasks[task.task_id]
                if task.task_id in self._task_states:
                    self._task_states[task.task_id].status = TaskStatus.FAILED
                    self._task_states[task.task_id].last_error = "Execution timed out"
            raise TaskTimeoutError(
                task_id=task.task_id,
                timeout_seconds=task.timeout_seconds or self._default_timeout,
                agent_id=task.agent_id,
            )
        except Exception as e:
            with self._lock:
                if task.task_id in self._task_states:
                    self._task_states[task.task_id].status = TaskStatus.FAILED
                    self._task_states[task.task_id].last_error = str(e)
            raise AgentError(
                message=f"Execution failed: {str(e)}",
                code="EXECUTOR_002",
                task_id=task.task_id,
                cause=e,
            )
    
    def _execute_task(
        self,
        task: TaskDefinition,
        plan: ExecutionPlan | None,
        workflow_id: str | None,
        context: Any,
        memory: Any,
        approval_callback: Callable[[dict[str, Any]], bool] | None,
        handoff_callback: Callable[[dict[str, Any]], bool] | None,
    ) -> ExecutionResult:
        """Internal task execution method."""
        start_time = time.time()
        execution = self._task_states.get(task.task_id)
        
        if not execution:
            execution = TaskExecution(
                task_id=task.task_id,
                agent_id=task.agent_id or "",
                status=TaskStatus.RUNNING,
                started_at=datetime.utcnow(),
            )
            with self._lock:
                self._task_states[task.task_id] = execution
        
        try:
            # Check concurrency limit
            if task.agent_id:
                self._check_concurrency(task.agent_id)
            
            # Execute with retries
            for attempt in range(max(task.max_retries, self._max_retries)):
                execution.attempt_count = attempt + 1
                
                try:
                    # Check budget
                    self._check_budget(task, execution)
                    
                    # Execute the task
                    result = self._run_agent_task(
                        task=task,
                        plan=plan,
                        workflow_id=workflow_id,
                        context=context,
                        memory=memory,
                        approval_callback=approval_callback,
                        handoff_callback=handoff_callback,
                    )
                    
                    execution.status = TaskStatus.COMPLETED
                    execution.completed_at = datetime.utcnow()
                    execution.result = result.get("result")
                    execution.decisions = result.get("decisions", [])
                    execution.tool_calls = result.get("tool_calls", [])
                    execution.handoffs = result.get("handoffs", [])
                    execution.approval_requests = result.get("approval_requests", [])
                    execution.budget_usage = result.get("budget_usage", {})
                    
                    return ExecutionResult(
                        task_id=task.task_id,
                        success=True,
                        result=execution.result,
                        attempt_count=execution.attempt_count,
                        duration_seconds=time.time() - start_time,
                        decisions=execution.decisions,
                        tool_calls=execution.tool_calls,
                        budget_usage=execution.budget_usage,
                        handoffs=execution.handoffs,
                        approval_requests=execution.approval_requests,
                    )
                    
                except ApprovalRequiredError as e:
                    # Handle approval required
                    if approval_callback:
                        approval_request = {
                            "task_id": task.task_id,
                            "reason": e.reason,
                            "required_permissions": e.required_permissions,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        if not approval_callback(approval_request):
                            raise
                    else:
                        raise
                        
                except AgentError as e:
                    execution.last_error = str(e)
                    execution.status = TaskStatus.FAILED
                    
                    # Check if we should retry
                    if attempt < max(task.max_retries, self._max_retries) - 1:
                        # Exponential backoff
                        backoff = (2 ** attempt) * 0.1
                        time.sleep(backoff)
                        continue
                    else:
                        raise MaxRetriesExceededError(
                            task_id=task.task_id,
                            max_retries=max(task.max_retries, self._max_retries),
                            attempt_count=execution.attempt_count,
                            agent_id=task.agent_id,
                        )
            
            # Should not reach here
            raise AgentError("Unexpected execution state", code="EXECUTOR_003", task_id=task.task_id)
            
        except TaskCancelledError:
            execution.status = TaskStatus.CANCELLED
            execution.completed_at = datetime.utcnow()
            raise
            
        except Exception as e:
            execution.status = TaskStatus.FAILED
            execution.last_error = str(e)
            execution.completed_at = datetime.utcnow()
            raise
    
    def _check_concurrency(self, agent_id: str) -> None:
        """Check if agent has exceeded concurrency limit."""
        with self._lock:
            agent = self._registry.get_agent(agent_id)
            current = self._agent_concurrency.get(agent_id, 0)
            
            # Get agent's concurrency limit from capabilities
            limit = 1
            for cap in agent.capabilities:
                if cap.concurrency_limit > limit:
                    limit = cap.concurrency_limit
            
            if current >= limit:
                raise ConcurrencyLimitError(agent_id, current, limit)
            
            self._agent_concurrency[agent_id] = current + 1
    
    def _release_concurrency(self, agent_id: str) -> None:
        """Release a concurrency slot for an agent."""
        with self._lock:
            if agent_id in self._agent_concurrency:
                self._agent_concurrency[agent_id] -= 1
    
    def _check_budget(self, task: TaskDefinition, execution: TaskExecution) -> None:
        """Check if task has exceeded its budget."""
        for budget_type, limit in task.budget.items():
            used = execution.budget_usage.get(budget_type, 0)
            if used >= limit:
                raise BudgetExceededError(
                    task_id=task.task_id,
                    budget_type=budget_type,
                    used=used,
                    limit=limit,
                    agent_id=task.agent_id,
                )
    
    def _run_agent_task(
        self,
        task: TaskDefinition,
        plan: ExecutionPlan | None,
        workflow_id: str | None,
        context: Any,
        memory: Any,
        approval_callback: Callable[[dict[str, Any]], bool] | None,
        handoff_callback: Callable[[dict[str, Any]], bool] | None,
    ) -> dict[str, Any]:
        """Run the actual agent task.
        
        This is where the agent-specific logic would be invoked.
        For now, this is a placeholder that needs to be extended.
        """
        # Get the agent
        if not task.agent_id:
            raise AgentError("No agent specified for task", code="EXECUTOR_004", task_id=task.task_id)
        
        try:
            agent = self._registry.get_agent(task.agent_id)
        except AgentNotFoundError:
            raise AgentNotFoundError(task.agent_id)
        
        # Check agent is available
        if not self._registry.check_agent_available(task.agent_id):
            raise AgentDisabledError(task.agent_id)
        
        # TODO: Actually invoke the agent
        # This would use the agent's specific implementation
        # For now, return a mock result
        
        result = {
            "result": {
                "status": "completed",
                "message": f"Task {task.task_id} executed by {agent.name}",
                "agent_id": task.agent_id,
                "agent_name": agent.name,
                "timestamp": datetime.utcnow().isoformat(),
            },
            "decisions": [],
            "tool_calls": [],
            "handoffs": [],
            "approval_requests": [],
            "budget_usage": {},
        }
        
        return result
    
    def cancel_task(self, task_id: str, reason: str | None = None) -> None:
        """Cancel a running task."""
        with self._lock:
            if task_id not in self._running_tasks:
                raise AgentError(
                    message=f"Task {task_id} not found or not running",
                    code="EXECUTOR_005",
                    task_id=task_id,
                )
            
            future = self._running_tasks[task_id]
            future.cancel()
            del self._running_tasks[task_id]
            
            if task_id in self._task_states:
                self._task_states[task_id].status = TaskStatus.CANCELLED
                self._task_states[task_id].last_error = reason or "Cancelled by user"
                self._task_states[task_id].completed_at = datetime.utcnow()
    
    def get_task_status(self, task_id: str) -> TaskExecution:
        """Get the current status of a task."""
        with self._lock:
            if task_id not in self._task_states:
                raise AgentError(
                    message=f"Task {task_id} not found",
                    code="EXECUTOR_006",
                    task_id=task_id,
                )
            return self._task_states[task_id]
    
    def list_tasks(
        self,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskExecution]:
        """List tasks with optional filters."""
        with self._lock:
            tasks = list(self._task_states.values())
            
            if status:
                tasks = [t for t in tasks if t.status == status]
            
            if agent_id:
                tasks = [t for t in tasks if t.agent_id == agent_id]
            
            # Sort by started_at descending
            tasks.sort(key=lambda t: t.started_at, reverse=True)
            
            return tasks[offset:offset + limit]
    
    def shutdown(self) -> None:
        """Shutdown the executor."""
        with self._lock:
            self._shutdown = True
            
        # Cancel all running tasks
        for task_id, future in list(self._running_tasks.items()):
            future.cancel()
        
        self._executor.shutdown(wait=True)


# Global executor instance
_executor: AgentExecutor | None = None
_executor_lock = threading.Lock()


def get_executor(
    max_concurrent_tasks: int = 10,
    max_retries: int = 3,
    default_timeout: float = 300.0,
) -> AgentExecutor:
    """Get the global executor instance."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = AgentExecutor(
                max_concurrent_tasks=max_concurrent_tasks,
                max_retries=max_retries,
                default_timeout=default_timeout,
            )
        return _executor


def reset_executor() -> None:
    """Reset the global executor (for testing)."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown()
        _executor = None
