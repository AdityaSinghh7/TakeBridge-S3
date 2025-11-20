"""MCP Agent - Clean modular architecture for ReAct-based MCP task execution."""

# New clean API
from .agent.entrypoint import execute_task
from .core.context import AgentContext
from .core.exceptions import MCPAgentError
from .registry.manager import RegistryManager
from .registry.oauth import OAuthManager

__all__ = [
    "execute_task",
    "AgentContext",
    "MCPAgentError",
    "RegistryManager",
    "OAuthManager",
]
