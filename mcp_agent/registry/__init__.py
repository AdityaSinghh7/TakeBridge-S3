"""Registry module: Source of truth for provider/tool configuration and OAuth."""

import importlib.util
import sys
from pathlib import Path

from .models import User, AuthConfig, ConnectedAccount, MCPConnection
from .crud import (
    upsert_user,
    upsert_auth_config,
    upsert_connected_account,
    upsert_mcp_connection,
    get_active_mcp_for_provider,
    get_active_context_for_provider,
    is_authorized,
    disconnect_provider,
    disconnect_account,
)

# Import compatibility functions from the old registry.py module
# This is needed because the old registry.py file still contains
# functions that are used by mcp_agent.py and other modules
_registry_module_path = Path(__file__).parent.parent / "registry.py"
if _registry_module_path.exists():
    spec = importlib.util.spec_from_file_location("mcp_agent._old_registry", _registry_module_path)
    if spec and spec.loader:
        _old_registry = importlib.util.module_from_spec(spec)
        sys.modules["mcp_agent._old_registry"] = _old_registry
        spec.loader.exec_module(_old_registry)
        
        # Re-export the functions needed by other modules
        get_client = _old_registry.get_client
        init_registry = _old_registry.init_registry
        is_registered = _old_registry.is_registered
        registry_version = _old_registry.registry_version
        get_configured_providers = getattr(_old_registry, "get_configured_providers", None)
        refresh_registry_from_oauth = getattr(_old_registry, "refresh_registry_from_oauth", None)
    else:
        # Fallback: define these as None if we can't load the module
        get_client = None
        init_registry = None
        is_registered = None
        registry_version = None
        get_configured_providers = None
        refresh_registry_from_oauth = None
else:
    # Old registry.py doesn't exist
    get_client = None
    init_registry = None
    is_registered = None
    registry_version = None
    get_configured_providers = None
    refresh_registry_from_oauth = None

__all__ = [
    # Models
    "User",
    "AuthConfig",
    "ConnectedAccount",
    "MCPConnection",
    # CRUD
    "upsert_user",
    "upsert_auth_config",
    "upsert_connected_account",
    "upsert_mcp_connection",
    "get_active_mcp_for_provider",
    "get_active_context_for_provider",
    "is_authorized",
    "disconnect_provider",
    "disconnect_account",
    # Compatibility exports from old registry.py
    "get_client",
    "init_registry",
    "is_registered",
    "registry_version",
]

