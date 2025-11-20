"""Backward compatibility shim for refactored mcp_agent modules.

Provides deprecated wrappers for old import paths to minimize breaking changes.
All new code should use the new module structure directly.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict

from mcp_agent.core.context import AgentContext
from mcp_agent.mcp_client import MCPClient
from mcp_agent.registry.manager import RegistryManager
from mcp_agent.registry.oauth import OAuthManager as NewOAuthManager
from mcp_agent.user_identity import normalize_user_id


def _deprecation_warning(old_path: str, new_path: str):
    """Emit a deprecation warning for old import paths."""
    warnings.warn(
        f"{old_path} is deprecated and will be removed in a future version. "
        f"Use {new_path} instead.",
        DeprecationWarning,
        stacklevel=3,
    )


# ==================== Old registry.py compatibility ====================


def init_registry(user_id: str) -> None:
    """
    Deprecated: Initialize MCP registry for a user.
    
    New code should use RegistryManager(context) instead.
    """
    _deprecation_warning("mcp_agent.registry.init_registry", "mcp_agent.registry.manager.RegistryManager")
    # No-op: registry is now DB-backed, no initialization needed
    pass


def get_client(provider: str, user_id: str) -> MCPClient | None:
    """
    Deprecated: Get MCP client for a provider.
    
    New code should use:
        context = AgentContext.create(user_id)
        registry = RegistryManager(context)
        client = registry.get_mcp_client(provider)
    """
    _deprecation_warning("mcp_agent.registry.get_client", "RegistryManager.get_mcp_client")
    
    try:
        context = AgentContext.create(user_id)
        registry = RegistryManager(context)
        return registry.get_mcp_client(provider)
    except Exception:
        return None


def is_registered(provider: str, user_id: str) -> bool:
    """
    Deprecated: Check if provider is registered.
    
    New code should use:
        context = AgentContext.create(user_id)
        registry = RegistryManager(context)
        registry.is_provider_available(provider)
    """
    _deprecation_warning("mcp_agent.registry.is_registered", "RegistryManager.is_provider_available")
    
    context = AgentContext.create(user_id)
    registry = RegistryManager(context)
    return registry.is_provider_available(provider)


def get_configured_providers(user_id: str) -> set[str]:
    """
    Deprecated: Get set of configured providers.
    
    New code should use:
        context = AgentContext.create(user_id)
        registry = RegistryManager(context)
        providers = registry.get_available_providers()
        configured = {p.provider for p in providers if p.configured}
    """
    _deprecation_warning("mcp_agent.registry.get_configured_providers", "RegistryManager.get_available_providers")
    
    context = AgentContext.create(user_id)
    registry = RegistryManager(context)
    providers = registry.get_available_providers()
    return {p.provider for p in providers if p.configured}


def refresh_registry_from_oauth(user_id: str) -> None:
    """
    Deprecated: Refresh registry from OAuth state.
    
    Registry is now DB-backed and auto-refreshes. This is a no-op.
    """
    _deprecation_warning("mcp_agent.registry.refresh_registry_from_oauth", "N/A (auto-refresh)")
    pass


def registry_version(user_id: str) -> int:
    """
    Deprecated: Get registry version.
    
    Registry versioning is no longer used. Returns 0.
    """
    _deprecation_warning("mcp_agent.registry.registry_version", "N/A (removed)")
    return 0


# ==================== Old oauth.py compatibility ====================


class OAuthManager:
    """
    Deprecated: OAuth manager compatibility wrapper.
    
    New code should use:
        from mcp_agent.registry.oauth import OAuthManager
        # All methods now require AgentContext as first parameter
    """
    
    @classmethod
    def start_oauth(cls, provider: str, user_id: str, redirect_uri: str) -> str:
        """Deprecated: Use OAuthManager.start_oauth(context, provider, redirect_uri)."""
        _deprecation_warning("OAuthManager.start_oauth (old signature)", "OAuthManager.start_oauth(context, ...)")
        context = AgentContext.create(user_id)
        return NewOAuthManager.start_oauth(context, provider, redirect_uri)
    
    @classmethod
    def finalize_connected_account(cls, provider: str, user_id: str, connected_account_id: str) -> Dict[str, Any]:
        """Deprecated: Use OAuthManager.finalize_connected_account(context, provider, ca_id)."""
        _deprecation_warning("OAuthManager.finalize_connected_account (old signature)", "OAuthManager.finalize_connected_account(context, ...)")
        context = AgentContext.create(user_id)
        return NewOAuthManager.finalize_connected_account(context, provider, connected_account_id)
    
    @classmethod
    def disconnect(cls, provider: str, user_id: str) -> None:
        """Deprecated: Use OAuthManager.disconnect(context, provider)."""
        _deprecation_warning("OAuthManager.disconnect (old signature)", "OAuthManager.disconnect(context, ...)")
        context = AgentContext.create(user_id)
        NewOAuthManager.disconnect(context, provider)
    
    @classmethod
    def is_authorized(cls, provider: str, user_id: str) -> bool:
        """Deprecated: Use OAuthManager.is_authorized(context, provider)."""
        _deprecation_warning("OAuthManager.is_authorized (old signature)", "OAuthManager.is_authorized(context, ...)")
        context = AgentContext.create(user_id)
        return NewOAuthManager.is_authorized(context, provider)
    
    @classmethod
    def get_mcp_url(cls, user_id: str, provider: str) -> str | None:
        """Deprecated: Use OAuthManager.get_mcp_url(context, provider)."""
        _deprecation_warning("OAuthManager.get_mcp_url (old signature)", "OAuthManager.get_mcp_url(context, ...)")
        context = AgentContext.create(user_id)
        return NewOAuthManager.get_mcp_url(context, provider)
    
    @classmethod
    def get_headers(cls, user_id: str, provider: str) -> Dict[str, str]:
        """Deprecated: Use OAuthManager.get_headers(context, provider)."""
        _deprecation_warning("OAuthManager.get_headers (old signature)", "OAuthManager.get_headers(context, ...)")
        context = AgentContext.create(user_id)
        return NewOAuthManager.get_headers(context, provider)
    
    @classmethod
    def sync(cls, provider: str, user_id: str, force: bool = False) -> None:
        """Deprecated: OAuth sync is no longer needed (DB-backed)."""
        _deprecation_warning("OAuthManager.sync", "N/A (removed)")
        pass
    
    @classmethod
    def set_redirect_hints(cls, provider: str, user_id: str, success_url: str | None = None, error_url: str | None = None) -> None:
        """Deprecated: Redirect hints should be managed by web layer."""
        _deprecation_warning("OAuthManager.set_redirect_hints", "N/A (moved to web layer)")
        pass
    
    @classmethod
    def consume_redirect_hint(cls, provider: str, user_id: str, success: bool) -> str | None:
        """Deprecated: Redirect hints should be managed by web layer."""
        _deprecation_warning("OAuthManager.consume_redirect_hint", "N/A (moved to web layer)")
        return None


# ==================== Old toolbox/builder.py compatibility ====================


def get_manifest(user_id: str, *, refresh: bool = False, persist: bool = True, base_dir: Any = None):
    """
    Deprecated: Get toolbox manifest.
    
    New code should use:
        from mcp_agent.toolbox.builder import get_manifest
        # Function signature unchanged but uses AgentContext internally
    """
    _deprecation_warning("mcp_agent.compat.get_manifest", "mcp_agent.toolbox.builder.get_manifest")
    from mcp_agent.toolbox.builder import get_manifest as new_get_manifest
    return new_get_manifest(user_id, refresh=refresh, persist=persist, base_dir=base_dir)


def get_index(user_id: str, *, base_dir: Any = None):
    """
    Deprecated: Get toolbox index.
    
    New code should use:
        from mcp_agent.toolbox.builder import get_index
        # Function signature unchanged but uses AgentContext internally
    """
    _deprecation_warning("mcp_agent.compat.get_index", "mcp_agent.toolbox.builder.get_index")
    from mcp_agent.toolbox.builder import get_index as new_get_index
    return new_get_index(user_id, base_dir=base_dir)


# ==================== Old planner/runtime.py compatibility ====================


def execute_mcp_task(task: str, *, user_id: str, **kwargs):
    """
    Deprecated: Execute MCP task.
    
    New code should use:
        from mcp_agent.agent import execute_task
        result = execute_task(task, user_id, **kwargs)
    """
    _deprecation_warning("mcp_agent.planner.runtime.execute_mcp_task", "mcp_agent.agent.execute_task")
    from mcp_agent.agent import execute_task
    return execute_task(task, user_id, **kwargs)


__all__ = [
    # Old registry.py
    "init_registry",
    "get_client",
    "is_registered",
    "get_configured_providers",
    "refresh_registry_from_oauth",
    "registry_version",
    # Old oauth.py
    "OAuthManager",
    # Old toolbox/builder.py
    "get_manifest",
    "get_index",
    # Old planner/runtime.py
    "execute_mcp_task",
]

