"""Actions layer - Tool wrappers and dispatching."""

from .provider_loader import discover_providers, load_action_map

# Discover providers dynamically based on wrapper modules
SUPPORTED_PROVIDERS: tuple[str, ...] = discover_providers()


# Keep the action map export for compatibility
def get_provider_action_map():
    """Get mapping of provider -> action functions."""
    return load_action_map(SUPPORTED_PROVIDERS)


def iter_available_action_functions(user_id=None):
    """
    Iterate over available action functions, yielding (provider, function).

    The optional user_id is accepted for backward compatibility; it is
    currently ignored because availability is already encoded in the wrapper
    registration.
    """
    action_map = get_provider_action_map()
    for provider, funcs in action_map.items():
        for func in funcs:
            yield provider, func


from .dispatcher import dispatch_tool

__all__ = [
    "dispatch_tool",
    "SUPPORTED_PROVIDERS",
    "get_provider_action_map",
    "iter_available_action_functions",
]
