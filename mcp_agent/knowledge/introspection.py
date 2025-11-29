"""Tool introspection - Building tool metadata from action wrappers.

Combines:
- Toolbox builder (manifest generation from action wrappers)
- IoToolSpec registry (for documentation/probing utilities)
- Lazy loading of IO specifications
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple, TYPE_CHECKING

from shared.streaming import emit_event

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

from mcp_agent.actions import get_provider_action_map
from mcp_agent.registry.oauth import OAuthManager
from mcp_agent.core.context import AgentContext
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.knowledge.types import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest, IoToolSpec
from mcp_agent.knowledge.index import ToolboxIndex
from mcp_agent.knowledge.utils import (
    action_signature,
    extract_call_tool_metadata,
    fingerprint_manifest,
    format_annotation,
    parse_action_docstring,
    relative_source_path,
    serialize_default,
    short_description,
    utcnow_iso,
)


# ============================================================================
# Toolbox manifest building and caching
# ============================================================================


CacheKey = str


@dataclass
class CacheEntry:
    manifest: ToolboxManifest
    registry_version: int


_MANIFEST_CACHE: Dict[CacheKey, CacheEntry] = {}
_MANIFEST_CACHE_LOCK = threading.RLock()


def _function_ast(func: Callable[..., object]) -> ast.AST | None:
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return None
    try:
        return ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _detect_helper_params(
    func: Callable[..., object], helper_names: List[str]
) -> Dict[str, set[str]]:
    tree = _function_ast(func)
    results: Dict[str, set[str]] = {name: set() for name in helper_names}
    if tree is None:
        return results
    try:
        param_names = set(inspect.signature(func).parameters.keys())
    except (TypeError, ValueError):
        param_names = set()

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            name = _call_name(node.func)
            if name in helper_names and node.args:
                first = node.args[0]
                if isinstance(first, ast.Name) and first.id in param_names:
                    results[name].add(first.id)
            self.generic_visit(node)

    Visitor().visit(tree)
    return results


class ToolboxBuilder:
    """Build tool metadata derived from MCP action wrappers (in-memory only)."""

    def __init__(self, *, user_id: str):
        self.user_id = normalize_user_id(user_id)
        self.generated_at = utcnow_iso()
        self.context = AgentContext.create(self.user_id)

    def build(self) -> ToolboxManifest:
        providers: List[ProviderSpec] = []
        for provider, funcs in sorted(get_provider_action_map().items()):
            status = OAuthManager.auth_status(self.context, provider)
            # Only include providers that are authorized and not refresh-blocked
            if not status.get("authorized"):
                continue
            providers.append(self._build_provider(provider, funcs, status))

        current_version = 0  # Registry versioning removed
        payload = {
            "user_id": self.user_id,
            "generated_at": self.generated_at,
            "registry_version": current_version,
            "providers": [provider.to_dict() for provider in providers],
        }
        fingerprint = fingerprint_manifest(payload)
        return ToolboxManifest(
            user_id=self.user_id,
            generated_at=self.generated_at,
            registry_version=current_version,
            fingerprint=fingerprint,
            providers=providers,
        )

    def _build_provider(
        self,
        provider: str,
        funcs: Tuple[Callable[..., object], ...],
        status: Dict[str, object],
    ) -> ProviderSpec:
        authorized = bool(status.get("authorized"))
        mcp_url = status.get("mcp_url") if isinstance(status, dict) else None

        # Simplified: registered field removed - redundant with authorized
        configured = bool(mcp_url) or authorized
        actions = [self._build_tool(provider, fn, authorized) for fn in funcs]
        return ProviderSpec(
            provider=provider,
            display_name=provider.capitalize(),
            authorized=authorized,
            configured=configured,
            mcp_url=mcp_url,
            actions=actions,
            last_refreshed=self.generated_at,
        )

    def _build_tool(
        self,
        provider: str,
        func: Callable[..., object],
        authorized: bool,
    ) -> ToolSpec:
        doc = inspect.getdoc(func) or ""
        description, param_docs = parse_action_docstring(doc)
        short_desc = short_description(description or doc, fallback=f"{provider}.{func.__name__}")
        signature = inspect.signature(func)
        parameters = []
        for param in signature.parameters.values():
            if param.name in ("self", "context"):
                continue
            annotation = format_annotation(param.annotation)
            default_value, default_repr = serialize_default(param.default)
            parameters.append(
                ParameterSpec(
                    name=param.name,
                    kind=str(param.kind).replace("Parameter.", "").lower(),
                    required=param.default is inspect._empty,
                    has_default=param.default is not inspect._empty,
                    annotation=annotation,
                    default=default_value,
                    default_repr=default_repr,
                    description=param_docs.get(param.name),
                )
            )

        return_annotation = format_annotation(signature.return_annotation)
        provider_literal, mcp_tool = extract_call_tool_metadata(func)
        # Simplified: available now just means authorized
        available = authorized
        if not authorized:
            reason = "unauthorized"
        else:
            reason = None
        source_path, source_line = relative_source_path(func)

        helpers = _detect_helper_params(
            func,
            [
                "_serialize_structured_param",
                "_norm_string_list",
                "_norm_recipients",
                "_primary_plus_rest",
            ],
        )
        structured_params = sorted(helpers.get("_serialize_structured_param", []))
        list_params: Dict[str, str] = {}
        for name in helpers.get("_norm_string_list", []):
            list_params[name] = "string_list"
        for name in helpers.get("_norm_recipients", []):
            list_params[name] = "recipient_list"
        primary_param = None
        primary_candidates = helpers.get("_primary_plus_rest", [])
        if primary_candidates:
            primary_param = sorted(primary_candidates)[0]

        raw_schema = getattr(func, "__tb_output_schema__", None)
        raw_schema_pretty = getattr(func, "__tb_output_schema_pretty__", None)
        if raw_schema_pretty is not None:
            pretty_lines = [line.rstrip() for line in str(raw_schema_pretty).strip().splitlines()]
        else:
            pretty_lines = [
                "Canonical wrapper: { success: bool, data: dict, error: str | null }",
                "",
                "data: <schema not documented; TODO: replace with real Composio-compatible response payload schema>",
            ]

        return ToolSpec(
            provider=provider_literal or provider,
            name=func.__name__,
            description=description or doc.strip(),
            short_description=short_desc,
            docstring=doc,
            python_name=func.__name__,
            python_signature=action_signature(func),
            parameters=parameters,
            mcp_tool_name=mcp_tool,
            oauth_provider=provider,
            oauth_required=True,
            available=available,
            availability_reason=reason,
            source_path=source_path,
            source_line=source_line,
            returns=return_annotation,
            structured_params=structured_params,
            list_params=list_params,
            primary_param=primary_param,
            output_schema=raw_schema or {},
            output_schema_pretty=pretty_lines,
        )


def get_manifest(
    user_id: str,
    *,
    refresh: bool = False,
) -> ToolboxManifest:
    """Return (and cache) the toolbox manifest for a user."""
    user = normalize_user_id(user_id)
    key = user
    # Helper to compute currently authorized providers (refresh-aware)
    def _current_authorized_set() -> set[str]:
        ctx = AgentContext.create(user)
        auth = set()
        for prov in get_provider_action_map().keys():
            status = OAuthManager.auth_status(ctx, prov)
            if status.get("authorized"):
                auth.add(prov)
        return auth

    with _MANIFEST_CACHE_LOCK:
        entry = _MANIFEST_CACHE.get(key)
        needs_refresh = (
            refresh
            or entry is None
            or entry.manifest.fingerprint is None
        )
        if not needs_refresh and entry is not None:
            cached_auth = {p.provider for p in entry.manifest.providers if p.authorized}
            current_auth = _current_authorized_set()
            if cached_auth != current_auth:
                needs_refresh = True

    if needs_refresh:
        builder = ToolboxBuilder(user_id=user)
        manifest = builder.build()
        entry = CacheEntry(
            manifest=manifest,
            registry_version=manifest.registry_version,
        )
        with _MANIFEST_CACHE_LOCK:
            _MANIFEST_CACHE[key] = entry
        emit_event(
            "mcp.toolbox.generated",
            {
                "user_id": user,
                "providers": len(manifest.providers),
                "persisted": False,
                "fingerprint": manifest.fingerprint,
            },
        )
        return manifest

    return entry.manifest


def invalidate_manifest_cache(user_id: str | None = None) -> None:
    normalized = None
    if user_id is not None:
        normalized = normalize_user_id(user_id)
    with _MANIFEST_CACHE_LOCK:
        if normalized is None:
            _MANIFEST_CACHE.clear()
            return
        _MANIFEST_CACHE.pop(normalized, None)


def get_index(
    user_id: str,
) -> ToolboxIndex:
    """
    Convenience helper to construct a ToolboxIndex for the given user.

    This reuses the manifest cache and does not persist any new files.
    Automatically invalidates cache and rebuilds if embeddings become available.
    """
    from .embeddings import get_embedding_service

    manifest = get_manifest(user_id=user_id)
    index = ToolboxIndex.from_manifest(manifest)

    # Check if embeddings were generated - if not, check if model is now available
    if not index.tool_embeddings:
        embedding_service = get_embedding_service()
        if embedding_service._ensure_model_loaded():
            # Model is now available, invalidate cache to rebuild with embeddings
            invalidate_manifest_cache(user_id)
            manifest = get_manifest(user_id=user_id, refresh=True)
            index = ToolboxIndex.from_manifest(manifest)

    return index


# ============================================================================
# IoToolSpec registry (for documentation and probing utilities)
# ============================================================================


_TOOL_REGISTRY: Dict[str, IoToolSpec] = {}
_IO_SPECS_LOADED: bool = False


def _registry_key(provider: str, tool_name: str) -> str:
    return f"{provider}.{tool_name}"


def register_tool(spec: IoToolSpec) -> None:
    """
    Register a tool specification for use by probing and documentation helpers.

    This registry is intentionally decoupled from the runtime toolbox index
    used by the planner.
    """
    _TOOL_REGISTRY[_registry_key(spec.provider, spec.tool_name)] = spec


def get_tool_spec(provider: str, tool_name: str) -> IoToolSpec | None:
    """Get IoToolSpec from registry (used by documentation/probing utilities)."""
    return _TOOL_REGISTRY.get(_registry_key(provider, tool_name))


def all_tools() -> List[IoToolSpec]:
    """Get all registered IoToolSpecs."""
    return list(_TOOL_REGISTRY.values())


def ensure_io_specs_loaded() -> None:
    """
    Lazily load output schemas from tool_output_schemas.generated.json.

    Registers basic IoToolSpecs from action wrappers, then enriches them
    with output schema information extracted from sample MCP responses.
    """
    global _IO_SPECS_LOADED
    if _IO_SPECS_LOADED:
        return

    from .schema_store import load_output_schemas
    from .types import ToolInputSpec, ToolOutputSpec

    # Register basic IoToolSpecs from action wrappers
    action_map: Dict[str, Tuple[Callable[..., object], ...]] = get_provider_action_map()
    for provider, funcs in action_map.items():
        for func in funcs:
            doc = inspect.getdoc(func) or ""
            sig = inspect.signature(func)

            # Create minimal IoToolSpec
            spec = IoToolSpec(
                provider=provider,
                tool_name=func.__name__,
                python_name=func.__name__,
                python_signature=str(sig),
                description=doc.strip() or f"{provider}.{func.__name__}",
                input_spec=ToolInputSpec(),
                output_spec=ToolOutputSpec(),
                func=None,
            )
            register_tool(spec)

    # Load and merge output schemas from JSON
    load_output_schemas()
    _IO_SPECS_LOADED = True
