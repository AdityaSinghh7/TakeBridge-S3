"""MCP Agent - Clean modular architecture for ReAct-based MCP task execution."""

# New clean API
from .agent import execute_mcp_task
from .core.context import AgentContext
from .core.exceptions import MCPAgentError
from .registry.oauth import OAuthManager

# Backward compatibility alias
execute_task = execute_mcp_task

__all__ = [
    "execute_task",
    "execute_mcp_task",
    "AgentContext",
    "MCPAgentError",
    "OAuthManager",
]
