"""MCP Agent: Multi-tenant ReAct agent for MCP tool orchestration.

New Architecture (Post-Refactor):
    - core: AgentContext and exceptions
    - registry: DB-backed provider/tool registry and OAuth
    - actions: Tool wrappers (gmail, slack)
    - knowledge: Metadata, search, and views
    - execution: I/O processing and sandbox
    - agent: ReAct planner and entry point

Backward Compatibility:
    - Old imports are available via compat module (deprecated)
    - Use new structure for all new code
"""

# New clean exports
from .agent import execute_task
from .core.context import AgentContext
from .core.exceptions import (
    MCPAgentError,
    ProviderNotFoundError,
    ToolExecutionError,
    ToolNotFoundError,
    UnauthorizedError,
)
from .registry.manager import RegistryManager

# Legacy compatibility (deprecated - import from compat explicitly)
# These will emit deprecation warnings
__all__ = [
    # New exports (primary API)
    "execute_task",
    "AgentContext",
    "RegistryManager",
    # Exceptions
    "MCPAgentError",
    "ProviderNotFoundError",
    "ToolNotFoundError",
    "UnauthorizedError",
    "ToolExecutionError",
]

