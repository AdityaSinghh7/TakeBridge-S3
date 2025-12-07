"""
Capability fetching infrastructure for the orchestrator agent.

This module provides functions to fetch and cache real-time capability information
from both the MCP agent (provider tree) and the computer-use agent (desktop environment).

Capabilities are cached with a 5-minute TTL to balance freshness vs performance.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, TYPE_CHECKING, List
from datetime import datetime, timedelta
import logging

if TYPE_CHECKING:
    from orchestrator_agent.data_types import OrchestratorRequest

logger = logging.getLogger(__name__)

# Global cache with TTL
_capability_cache: Dict[str, tuple[Dict[str, Any], datetime]] = {}
CACHE_TTL = timedelta(minutes=5)  # 5-minute TTL


def _resolve_controller(metadata: Dict[str, Any]):
    """
    Prefer a real controller client from metadata; otherwise build from config/env.
    """
    try:
        from server.api.controller_client import VMControllerClient  # Late import to avoid hard dependency
    except Exception:  # pragma: no cover - optional dependency
        VMControllerClient = None  # type: ignore

    controller = metadata.get("controller_client") or metadata.get("controller")

    if VMControllerClient and isinstance(controller, VMControllerClient):
        return controller

    if VMControllerClient and isinstance(controller, dict):
        try:
            return VMControllerClient(
                base_url=controller.get("base_url"),
                host=controller.get("host"),
                port=controller.get("port"),
                timeout=controller.get("timeout"),
            )
        except Exception as exc:  # pragma: no cover - guard against bad config
            logger.warning(f"Failed to initialize controller from metadata: {exc}")

    # Fallback: try environment-based construction
    if VMControllerClient:
        try:
            return VMControllerClient()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Failed to initialize controller from environment: {exc}")

    return None


def _normalize_platform(raw: Optional[str]) -> str:
    """
    Normalize platform strings to the values expected by the computer-use agent.
    """
    if not raw:
        return "unknown"
    val = str(raw).strip().lower()
    if val in {"mac", "macos", "osx", "mac os", "mac os x"}:
        return "darwin"
    if val in {"win", "windows", "win32"}:
        return "windows"
    if val in {"linux", "ubuntu", "debian", "fedora", "arch", "centos"}:
        return "linux"
    return val


def fetch_mcp_capabilities(user_id: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch available MCP providers and tools for a user.
    Uses mcp_agent.knowledge.search.get_inventory_view()

    Cached for 5 minutes per user to reduce latency and API load.

    Args:
        user_id: The user ID to fetch capabilities for
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        Dict containing provider tree:
        {
            "providers": [
                {"provider": "gmail", "tools": ["gmail_send_email", ...]},
                {"provider": "slack", "tools": ["slack_post_message", ...]}
            ]
        }
    """
    user_id_str = str(user_id)
    cache_key = f"mcp:{user_id_str}"

    # Check cache
    if not force_refresh and cache_key in _capability_cache:
        cached_data, cached_at = _capability_cache[cache_key]
        if datetime.utcnow() - cached_at < CACHE_TTL:
            logger.debug(f"Using cached MCP capabilities for user {user_id_str}")
            return cached_data

    # Fetch fresh data
    try:
        from mcp_agent.knowledge.search import get_inventory_view
        from mcp_agent.core.context import AgentContext

        context = AgentContext(user_id=user_id_str)
        inventory = get_inventory_view(context)

        # Cache the result
        _capability_cache[cache_key] = (inventory, datetime.utcnow())
        logger.debug(f"Fetched and cached MCP capabilities for user {user_id_str}")
        return inventory

    except Exception as e:
        logger.warning(f"Failed to fetch MCP capabilities: {e}", exc_info=True)
        return {"providers": []}


def fetch_computer_capabilities(
    request: "OrchestratorRequest", force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Fetch desktop environment state from controller API.

    Cached for 5 minutes to reduce VM controller API load.

    Args:
        request: Orchestration request containing controller in metadata
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        Dict containing desktop environment state:
        {
            "platform": "macos",
            "available_apps": ["Chrome", "Slack", "Excel", ...],
            "active_windows": [
                {"app_name": "Chrome", "title": "Dashboard"},
                {"app_name": "Excel", "title": "Revenue.xlsx"}
            ]
        }
    """
    # Use controller from request metadata
    controller = _resolve_controller(request.metadata)
    if not controller:
        logger.warning("No controller available from metadata or environment")
        return {"platform": "unknown", "available_apps": [], "active_windows": [], "actions": []}

    cache_key = f"computer:{request.user_id or 'default'}"

    # Check cache
    if not force_refresh and cache_key in _capability_cache:
        cached_data, cached_at = _capability_cache[cache_key]
        if datetime.utcnow() - cached_at < CACHE_TTL:
            logger.debug("Using cached computer capabilities")
            return cached_data

    # Fetch fresh data
    try:
        # Platform should come from the VM, not CLI flags.
        try:
            platform_raw = controller.get_platform()
        except Exception:
            platform_raw = None
        platform = _normalize_platform(platform_raw)

        apps_data = controller.get_apps(exclude_system=True)
        windows_data = controller.get_active_windows(exclude_system=True)

        # Surface available OSWorld agent actions (click, type, scroll, etc.)
        actions: List[str] = []
        try:
            from computer_use_agent.grounding.grounding_agent import (
                list_osworld_agent_actions,
            )

            actions = list_osworld_agent_actions()
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Unable to load OSWorld agent actions: %s", exc)

        # Persist the resolved platform back into request metadata for downstream use
        try:
            request.metadata["platform"] = platform
        except Exception:
            pass

        result = {
            "platform": platform or "unknown",
            "available_apps": (
                apps_data.get("apps", []) if isinstance(apps_data, dict) else []
            ),
            "active_windows": (
                windows_data.get("windows", [])
                if isinstance(windows_data, dict)
                else []
            ),
            "actions": actions,
        }

        # Cache the result
        _capability_cache[cache_key] = (result, datetime.utcnow())
        logger.debug("Fetched and cached computer capabilities")
        return result

    except Exception as e:
        logger.warning(f"Failed to fetch computer capabilities: {e}", exc_info=True)
        return {"platform": "unknown", "available_apps": [], "active_windows": []}


def build_capability_context(
    request: "OrchestratorRequest", force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Combine MCP and computer-use capabilities into structured context.

    Args:
        request: Orchestration request
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        Combined capabilities dictionary:
        {
            "mcp": {"providers": [...]},
            "computer": {"platform": ..., "available_apps": ..., "active_windows": ...}
        }
    """
    mcp_caps = fetch_mcp_capabilities(request.user_id or "default", force_refresh)
    computer_caps = fetch_computer_capabilities(request, force_refresh)

    return {
        "mcp": mcp_caps,
        "computer": computer_caps,
    }


def invalidate_cache(user_id: str) -> None:
    """
    Invalidate cached capabilities for a user.

    Useful when:
    - User connects a new OAuth provider
    - Desktop environment changes significantly
    - Manual cache refresh is needed

    Args:
        user_id: The user ID whose cache should be invalidated
    """
    mcp_key = f"mcp:{user_id}"
    computer_key = f"computer:{user_id}"

    if mcp_key in _capability_cache:
        del _capability_cache[mcp_key]
        logger.debug(f"Invalidated MCP cache for user {user_id}")

    if computer_key in _capability_cache:
        del _capability_cache[computer_key]
        logger.debug(f"Invalidated computer cache for user {user_id}")


__all__ = [
    "fetch_mcp_capabilities",
    "fetch_computer_capabilities",
    "build_capability_context",
    "invalidate_cache",
    "CACHE_TTL",
]
