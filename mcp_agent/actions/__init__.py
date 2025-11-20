"""Actions layer - Tool wrappers and dispatching."""

from .dispatcher import dispatch_tool

# Keep the action map export for compatibility
def get_provider_action_map():
    """Get mapping of provider -> action functions."""
    from .wrappers import gmail, slack
    import inspect
    
    result = {}
    
    # Collect gmail actions
    gmail_funcs = []
    for name, obj in inspect.getmembers(gmail):
        if callable(obj) and not name.startswith('_') and hasattr(obj, '__module__'):
            if 'gmail' in obj.__module__:
                gmail_funcs.append(obj)
    if gmail_funcs:
        result['gmail'] = tuple(gmail_funcs)
    
    # Collect slack actions
    slack_funcs = []
    for name, obj in inspect.getmembers(slack):
        if callable(obj) and not name.startswith('_') and hasattr(obj, '__module__'):
            if 'slack' in obj.__module__:
                slack_funcs.append(obj)
    if slack_funcs:
        result['slack'] = tuple(slack_funcs)
    
    return result


def iter_available_action_functions():
    """Iterate over all available action functions."""
    action_map = get_provider_action_map()
    for provider, funcs in action_map.items():
        for func in funcs:
            yield func


# Legacy compatibility functions
def configure_mcp_action_filters(*args, **kwargs):
    """Legacy compatibility - no-op."""
    pass


def describe_available_actions(*args, **kwargs):
    """Legacy compatibility."""
    action_map = get_provider_action_map()
    result = []
    for provider, funcs in action_map.items():
        for func in funcs:
            result.append({
                'provider': provider,
                'name': func.__name__,
                'description': (func.__doc__ or '').strip().split('\n')[0],
            })
    return result


__all__ = [
    "dispatch_tool",
    "get_provider_action_map",
    "iter_available_action_functions",
    "configure_mcp_action_filters",
    "describe_available_actions",
]
