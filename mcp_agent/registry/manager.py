"""Unified registry manager for MCP providers and tools.

Replaces global registry dict with context-aware DB queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Tuple

from mcp_agent.core.exceptions import ProviderNotFoundError, UnauthorizedError
from mcp_agent.mcp_client import MCPClient
from mcp_agent.user_identity import normalize_user_id

from . import crud
from .oauth import OAuthManager

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


@dataclass
class ProviderInfo:
    """Provider metadata."""
    provider: str
    authorized: bool
    configured: bool
    mcp_url: str | None


@dataclass
class ToolInfo:
    """Tool metadata."""
    provider: str
    name: str
    available: bool
    reason: str | None = None


class RegistryManager:
    """
    Unified registry manager for MCP providers and tools.
    
    Replaces global MCP_BY_USER dict with context-aware operations.
    All state is stored in the database.
    """
    
    def __init__(self, context: AgentContext):
        """
        Initialize registry manager.
        
        Args:
            context: Agent context with user_id and db_session
        """
        self.context = context
        self.user_id = normalize_user_id(context.user_id)
    
    def get_available_providers(self) -> List[ProviderInfo]:
        """
        Get list of available providers for the current user.
        
        Returns:
            List of ProviderInfo objects
        """
        from mcp_agent.actions import SUPPORTED_PROVIDERS
        
        providers = []
        with self.context.get_db() as db:
            for provider in SUPPORTED_PROVIDERS:
                mcp_url, _ = crud.get_active_mcp_for_provider(db, self.user_id, provider)
                authorized = bool(mcp_url)
                configured = bool(mcp_url)
                
                providers.append(
                    ProviderInfo(
                        provider=provider,
                        authorized=authorized,
                        configured=configured,
                        mcp_url=mcp_url,
                    )
                )
        
        return providers
    
    def get_provider_tools(self, provider: str) -> List[ToolInfo]:
        """
        Get list of tools for a provider.
        
        Args:
            provider: Provider name
        
        Returns:
            List of ToolInfo objects
        """
        from mcp_agent.actions import get_provider_action_map
        
        action_map = get_provider_action_map()
        funcs = action_map.get(provider, ())
        
        is_available, reason = self.check_availability(provider)
        
        tools = []
        for func in funcs:
            tools.append(
                ToolInfo(
                    provider=provider,
                    name=func.__name__,
                    available=is_available,
                    reason=reason if not is_available else None,
                )
            )
        
        return tools
    
    def check_availability(self, provider: str, tool: str | None = None) -> Tuple[bool, str]:
        """
        Check if a provider (and optionally tool) is available.
        
        Args:
            provider: Provider name
            tool: Optional tool name
        
        Returns:
            Tuple of (is_available, reason)
            - is_available: True if provider/tool is usable
            - reason: Human-readable explanation if not available
        """
        # Check if provider is authorized
        with self.context.get_db() as db:
            authorized = crud.is_authorized(db, self.user_id, provider)
        
        if not authorized:
            return False, f"Provider '{provider}' is not authorized for user '{self.user_id}'"
        
        # Check if tool exists (if specified)
        if tool:
            from mcp_agent.actions import get_provider_action_map
            
            action_map = get_provider_action_map()
            funcs = action_map.get(provider, ())
            tool_exists = any(f.__name__ == tool for f in funcs)
            
            if not tool_exists:
                return False, f"Tool '{tool}' not found for provider '{provider}'"
        
        return True, "available"
    
    def get_mcp_client(self, provider: str) -> MCPClient:
        """
        Get an MCP client for a provider.
        
        Args:
            provider: Provider name
        
        Returns:
            Configured MCPClient instance
        
        Raises:
            ProviderNotFoundError: If provider is not configured
            UnauthorizedError: If user is not authorized
        """
        with self.context.get_db() as db:
            mcp_url, _ = crud.get_active_mcp_for_provider(db, self.user_id, provider)
        
        if not mcp_url:
            # Check if provider exists at all
            from mcp_agent.actions import SUPPORTED_PROVIDERS
            
            if provider not in SUPPORTED_PROVIDERS:
                raise ProviderNotFoundError(
                    provider,
                    details={"user_id": self.user_id},
                )
            
            # Provider exists but not authorized
            raise UnauthorizedError(
                provider,
                self.user_id,
                details={"message": "OAuth connection required"},
            )
        
        # Get headers from OAuth manager
        headers = OAuthManager.get_headers(self.context, provider)
        
        return MCPClient(mcp_url, headers=headers)
    
    def is_provider_available(self, provider: str) -> bool:
        """
        Quick check if a provider is available.
        
        Args:
            provider: Provider name
        
        Returns:
            True if provider is authorized and configured
        """
        with self.context.get_db() as db:
            return crud.is_authorized(db, self.user_id, provider)
    
    def disconnect_provider(self, provider: str) -> Dict[str, int]:
        """
        Disconnect a provider for the current user.
        
        Args:
            provider: Provider name
        
        Returns:
            Dict with updated_accounts and cleared_connections counts
        """
        with self.context.get_db() as db:
            return crud.disconnect_provider(db, self.user_id, provider)

