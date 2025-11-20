"""Standardized exception hierarchy for MCP Agent operations."""

from __future__ import annotations


class MCPAgentError(Exception):
    """Base exception for all MCP Agent errors."""
    
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderNotFoundError(MCPAgentError):
    """Raised when a requested provider is not configured."""
    
    def __init__(self, provider: str, details: dict | None = None):
        message = f"Provider '{provider}' is not configured or not available."
        super().__init__(message, details)
        self.provider = provider


class ToolNotFoundError(MCPAgentError):
    """Raised when a requested tool does not exist."""
    
    def __init__(self, provider: str, tool: str, details: dict | None = None):
        message = f"Tool '{tool}' not found for provider '{provider}'."
        super().__init__(message, details)
        self.provider = provider
        self.tool = tool


class UnauthorizedError(MCPAgentError):
    """Raised when a user is not authorized for a provider/tool."""
    
    def __init__(self, provider: str, user_id: str, details: dict | None = None):
        message = f"User '{user_id}' is not authorized for provider '{provider}'."
        super().__init__(message, details)
        self.provider = provider
        self.user_id = user_id


class ToolExecutionError(MCPAgentError):
    """Raised when tool execution fails."""
    
    def __init__(self, provider: str, tool: str, error: str, details: dict | None = None):
        message = f"Tool '{provider}.{tool}' execution failed: {error}"
        super().__init__(message, details)
        self.provider = provider
        self.tool = tool
        self.error = error

