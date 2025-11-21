"""Actions layer - Tool wrappers and dispatching."""

from .dispatcher import dispatch_tool

# Static list of supported provider modules. Update this when adding/removing
# wrappers in ``mcp_agent/actions/wrappers``.
SUPPORTED_PROVIDERS: tuple[str, ...] = ("gmail", "slack")

# Keep the action map export for compatibility
def get_provider_action_map():
    """Get mapping of provider -> action functions."""
    import importlib
    import inspect

    result = {}

    for provider in SUPPORTED_PROVIDERS:
        module = importlib.import_module(f"mcp_agent.actions.wrappers.{provider}")
        funcs = []
        for name, obj in inspect.getmembers(module):
            if callable(obj) and not name.startswith("_") and hasattr(obj, "__module__"):
                if provider in obj.__module__:
                    funcs.append(obj)
        if funcs:
            result[provider] = tuple(funcs)

    return result


def iter_available_action_functions():
    """Iterate over all available action functions."""
    action_map = get_provider_action_map()
    for provider, funcs in action_map.items():
        for func in funcs:
            yield func


__all__ = [
    "dispatch_tool",
    "SUPPORTED_PROVIDERS",
    "get_provider_action_map",
    "iter_available_action_functions",
]
