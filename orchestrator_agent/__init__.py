"""
Starter package for the orchestrator agent.

Exports the runtime and canonical types so other packages can import from a
single place once real integrations are wired in.
"""

from orchestrator_agent.data_types import (
    AgentTarget,
    AgentTaskInput,
    Budget,
    CompletionReason,
    ComputerUseAgentOutput,
    MCPAgentOutput,
    OrchestratorContext,
    OrchestratorRequest,
    PlannedStep,
    RunState,
    StepResult,
    StepStatus,
    TenantContext,
    generate_step_id,
)
from orchestrator_agent.bridges import (
    run_agent_bridge,
    run_computer_use_agent,
    run_mcp_agent,
)
from orchestrator_agent.runtime import OrchestratorRuntime
from orchestrator_agent.system_prompt import (
    get_system_prompt,
    build_system_prompt,
)
from orchestrator_agent.translator import (
    TRANSLATOR_SYSTEM_PROMPT,
    translate_step_output,
)
from orchestrator_agent.capabilities import (
    build_capability_context,
    fetch_mcp_capabilities,
    fetch_computer_capabilities,
    invalidate_cache,
    CACHE_TTL,
)

__all__ = [
    "AgentTarget",
    "AgentTaskInput",
    "Budget",
    "CompletionReason",
    "ComputerUseAgentOutput",
    "MCPAgentOutput",
    "OrchestratorContext",
    "OrchestratorRequest",
    "OrchestratorRuntime",
    "PlannedStep",
    "RunState",
    "StepResult",
    "StepStatus",
    "TenantContext",
    "generate_step_id",
    "run_agent_bridge",
    "run_computer_use_agent",
    "run_mcp_agent",
    "TRANSLATOR_SYSTEM_PROMPT",
    "translate_step_output",
    "get_system_prompt",
    "build_system_prompt",
    "build_capability_context",
    "fetch_mcp_capabilities",
    "fetch_computer_capabilities",
    "invalidate_cache",
    "CACHE_TTL",
]
