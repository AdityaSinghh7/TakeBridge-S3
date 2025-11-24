from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Callable, Dict, Tuple


def discover_providers() -> Tuple[str, ...]:
    """
    Discover provider wrapper modules under mcp_agent.actions.wrappers.

    Skips private/helper modules prefixed with an underscore.
    """
    from . import wrappers as wrappers_pkg

    names = []
    for module in pkgutil.iter_modules(wrappers_pkg.__path__):
        if module.name.startswith("_"):
            continue
        names.append(module.name)
    return tuple(sorted(names))


def load_action_map(providers: Tuple[str, ...]) -> Dict[str, Tuple[Callable[..., object], ...]]:
    """
    Import wrapper modules for the given providers and collect public callables.

    Only includes functions defined in the provider module itself, not imported items.
    """
    result: Dict[str, Tuple[Callable[..., object], ...]] = {}
    for provider in providers:
        module = importlib.import_module(f"mcp_agent.actions.wrappers.{provider}")
        funcs = []
        for name, obj in inspect.getmembers(module):
            # Only include callables that:
            # - Don't start with underscore (public)
            # - Are actually functions (not classes or types)
            # - Are defined in this module (not imported)
            if (
                callable(obj)
                and not name.startswith("_")
                and inspect.isfunction(obj)
                and hasattr(obj, "__module__")
                and obj.__module__ == module.__name__
            ):
                funcs.append(obj)
        if funcs:
            result[provider] = tuple(funcs)
    return result
