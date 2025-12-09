from __future__ import annotations

"""
Canonical orchestrator data types.

This module is the single source of truth for request/state/result shapes
consumed by the orchestrator agent. Keeping the types centralized avoids
drift between the agents that will plug into this orchestrator.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

AgentTarget = Literal["mcp", "computer_use"]
StepStatus = Literal["pending", "running", "completed", "failed"]
CompletionReason = Literal["ok", "max_steps", "budget_exceeded", "error", "cancelled"]


@dataclass
class ToolConstraints:
    """Tool availability constraints for MCP agent.

    Controls which tools are available during task execution:
    - auto mode: Uses all tools from authorized providers (OAuth-verified)
    - custom mode: Restricts to specific providers/tools from the allow list
    """

    mode: Literal["auto", "custom"] = "auto"
    providers: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mode": self.mode,
            "providers": self.providers,
            "tools": self.tools,
        }


def generate_step_id(prefix: str = "step") -> str:
    """Small helper to keep step IDs consistent across the orchestrator."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@dataclass
class Budget:
    """Controls how long a run is allowed to proceed."""

    max_steps: int = 15
    max_cost_usd: Optional[float] = None
    max_tokens: Optional[int] = None

    def within_limits(
        self,
        step_count: int,
        cost_delta: float,
        *,
        tokens_spent: Optional[int] = None,
    ) -> bool:
        step_ok = step_count < self.max_steps
        cost_ok = self.max_cost_usd is None or cost_delta <= self.max_cost_usd
        token_ok = (
            True
            if self.max_tokens is None or tokens_spent is None
            else tokens_spent <= self.max_tokens
        )
        return step_ok and cost_ok and token_ok


@dataclass
class TenantContext:
    """Multi-tenant context to keep runs isolated and auditable."""

    tenant_id: str
    request_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class AgentTaskInput:
    """
    Input for both MCP and computer-use agents.

    This is the minimum payload required to route a task to either agent,
    keeping the contract symmetric across both.
    """

    task: str
    max_steps: int
    tenant: Optional[TenantContext] = None
    platform: Optional[str] = None
    allow_code_execution: bool = False
    budget: Budget = field(default_factory=Budget)
    metadata: Dict[str, Any] = field(default_factory=dict)
    preferred_agents: Optional[List[AgentTarget]] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTaskInput":
        return cls(
            task=data["task"],
            max_steps=int(data.get("max_steps", 15)),
            tenant=data.get("tenant"),
            platform=data.get("platform"),
            allow_code_execution=bool(data.get("allow_code_execution", False)),
            budget=data.get("budget")
            or Budget(
                max_steps=int(data.get("max_steps", 15)),
                max_cost_usd=data.get("max_cost_usd"),
            ),
            metadata=dict(data.get("metadata") or {}),
            preferred_agents=data.get("preferred_agents"),
            request_id=data.get("request_id"),
            user_id=data.get("user_id"),
        )


@dataclass
class MCPAgentOutput:
    """Normalized output from mcp_agent.agent.execute_mcp_task(...)."""

    success: bool
    final_summary: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    run_id: Optional[str] = None
    raw_outputs: Dict[str, Any] = field(default_factory=dict)
    budget_usage: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "MCPAgentOutput":
        return cls(
            success=bool(result.get("success", False)),
            final_summary=result.get("final_summary"),
            error=result.get("error"),
            error_code=result.get("error_code"),
            error_message=result.get("error_message"),
            error_details=dict(result.get("error_details") or {}),
            user_id=result.get("user_id"),
            run_id=result.get("run_id"),
            raw_outputs=dict(result.get("raw_outputs") or {}),
            budget_usage=dict(result.get("budget_usage") or {}),
            logs=list(result.get("logs") or []),
            steps=list(result.get("steps") or []),
        )


@dataclass
class ComputerUseAgentOutput:
    """Normalized output from computer_use_agent orchestrator `_perform_run`."""

    task: str
    status: str
    completion_reason: str
    steps: List[Dict[str, Any]]
    grounding_prompts: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "ComputerUseAgentOutput":
        return cls(
            task=result.get("task", ""),
            status=result.get("status", ""),
            completion_reason=result.get("completion_reason", ""),
            steps=list(result.get("steps") or []),
            grounding_prompts=dict(result.get("grounding_prompts") or {}),
            error=result.get("error"),
            raw=result,
        )


@dataclass
class OrchestratorRequest(AgentTaskInput):
    """Concrete request used by the orchestrator runtime."""

    tool_constraints: Optional[ToolConstraints] = None
    # Optional composed plan provided by the Task Compose Agent / frontend.
    # This should be a JSON-serializable dict matching the ComposedPlan schema.
    composed_plan: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        # Keep budget max_steps aligned with the top-level field.
        if self.budget and self.budget.max_steps != self.max_steps:
            self.budget.max_steps = self.max_steps

    @classmethod
    def from_task(
        cls,
        tenant_id: str,
        task: str,
        *,
        max_steps: Optional[int] = None,
        request_id: Optional[str] = None,
        budget: Optional[Budget] = None,
        metadata: Optional[Dict[str, Any]] = None,
        preferred_agents: Optional[List[AgentTarget]] = None,
        platform: Optional[str] = None,
        allow_code_execution: bool = False,
        user_id: Optional[str] = None,
    ) -> "OrchestratorRequest":
        """Helper for quick ad-hoc requests."""
        resolved_max_steps = (
            max_steps if max_steps is not None else (budget.max_steps if budget else 15)
        )
        ctx = TenantContext(
            tenant_id=tenant_id,
            request_id=request_id or tenant_id,
            user_id=user_id,
        )
        return cls(
            task=task,
            max_steps=resolved_max_steps,
            tenant=ctx,
            platform=platform,
            allow_code_execution=allow_code_execution,
            budget=budget or Budget(max_steps=resolved_max_steps),
            metadata=metadata or {},
            preferred_agents=preferred_agents,
            request_id=request_id or tenant_id,
            user_id=user_id,
        )


@dataclass
class PlannedStep:
    """
    Canonical step input for the orchestrator.

    Each step carries a target agent and the canonical routing payload
    (next_task, max_steps, verification) so step outputs mirror the inputs.
    """

    next_task: str
    max_steps: int
    verification: str
    target: AgentTarget
    step_id: str = field(default_factory=generate_step_id)
    description: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    hints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    requested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StepResult:
    """
    Execution details reported by the downstream agent.

    Mirrors PlannedStep fields so the orchestrator's stepwise inputs and
    outputs share a single canonical shape.
    """

    step_id: str
    target: AgentTarget
    next_task: str
    verification: str
    status: StepStatus
    success: Optional[bool] = None
    max_steps: Optional[int] = None
    description: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    hints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Default success flag to match status when not explicitly provided
        if self.success is None:
            self.success = self.status == "completed"

    @classmethod
    def from_planned(
        cls,
        planned: PlannedStep,
        *,
        status: StepStatus = "pending",
        success: bool = False,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        artifacts: Optional[Dict[str, Any]] = None,
    ) -> "StepResult":
        return cls(
            step_id=planned.step_id,
            target=planned.target,
            next_task=planned.next_task,
            verification=planned.verification,
            status=status,
            success=success,
            max_steps=planned.max_steps,
            description=planned.description,
            depends_on=list(planned.depends_on),
            hints=dict(planned.hints),
            metadata=dict(planned.metadata),
            output=output or {},
            error=error,
            started_at=started_at,
            finished_at=finished_at,
            artifacts=artifacts or {},
        )


@dataclass
class OrchestratorContext:
    """Context window carrying stepwise inputs/outputs for a run."""

    initial_task: str
    step_inputs: List[PlannedStep] = field(default_factory=list)
    step_outputs: List[StepResult] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tenant: Optional[TenantContext] = None
    request_id: Optional[str] = None
    cumulative_cost_usd: float = 0.0
    token_usage: Dict[str, Any] = field(default_factory=dict)

    def add_step_input(self, step: PlannedStep) -> None:
        self.step_inputs.append(step)

    def add_step_output(self, result: StepResult) -> None:
        self.step_outputs.append(result)

    def step_statuses(self) -> List[StepStatus]:
        return [result.status for result in self.step_outputs]

    def step_success_flags(self) -> List[bool]:
        return [result.success for result in self.step_outputs]

    def last_output(self) -> Optional[StepResult]:
        return self.step_outputs[-1] if self.step_outputs else None


@dataclass
class RunState:
    """Per-run state tracked inside the outer loop."""

    request: OrchestratorRequest
    plan: List[PlannedStep] = field(default_factory=list)
    results: List[StepResult] = field(default_factory=list)
    intermediate: Dict[str, Any] = field(default_factory=dict)
    cost_baseline: float = 0.0

    def pending_steps(self) -> List[PlannedStep]:
        completed = {result.step_id for result in self.results}
        return [step for step in self.plan if step.step_id not in completed]

    def record_intermediate(self, key: str, value: Any) -> None:
        self.intermediate[key] = value

    def record_result(self, result: StepResult) -> None:
        self.results.append(result)

    def total_steps(self) -> int:
        return len(self.results)

    def cost_exceeded(self, current_cost_total: float) -> bool:
        spent = max(current_cost_total - self.cost_baseline, 0.0)
        budget = self.request.budget
        if budget.max_cost_usd is None:
            return False
        return spent > budget.max_cost_usd

    def within_limits(self, current_cost_total: float) -> bool:
        spent = max(current_cost_total - self.cost_baseline, 0.0)
        tokens_spent = None
        return self.request.budget.within_limits(
            self.total_steps(),
            spent,
            tokens_spent=tokens_spent,
        )

    def context_window(self) -> OrchestratorContext:
        return OrchestratorContext(
            initial_task=self.request.task,
            step_inputs=list(self.plan),
            step_outputs=list(self.results),
            run_id=self.request.request_id or uuid.uuid4().hex,
            tenant=self.request.tenant,
            request_id=self.request.request_id,
            cumulative_cost_usd=0.0,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize RunState to a dict for persistence."""
        return {
            "status": "running",
            "loop_iteration": len(self.results),
            "cost_baseline": self.cost_baseline,
            "plan": [asdict(step) for step in self.plan],
            "results": [asdict(result) for result in self.results],
            "intermediate": self.intermediate,
            "pending_steps": [asdict(step) for step in self.pending_steps()],
        }


__all__ = [
    "AgentTarget",
    "AgentTaskInput",
    "Budget",
    "CompletionReason",
    "ComputerUseAgentOutput",
    "MCPAgentOutput",
    "OrchestratorContext",
    "OrchestratorRequest",
    "PlannedStep",
    "RunState",
    "StepResult",
    "StepStatus",
    "TenantContext",
    "ToolConstraints",
    "generate_step_id",
]
