"""Knowledge builder: Generate tool metadata from action wrappers."""

from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple, TYPE_CHECKING
import threading

from shared.streaming import emit_event

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

from mcp_agent.actions import get_provider_action_map
from mcp_agent.registry.oauth import OAuthManager
from mcp_agent.core.context import AgentContext
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.knowledge.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
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

    def build(self) -> ToolboxManifest:
        # No initialization needed - registry is DB-backed
        
        providers: List[ProviderSpec] = []
        for provider, funcs in sorted(get_provider_action_map().items()):
            providers.append(self._build_provider(provider, funcs))
        
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
        self, provider: str, funcs: Tuple[Callable[..., object], ...]
    ) -> ProviderSpec:
        # Use new context-based approach
        context = AgentContext.create(self.user_id)
        authorized = OAuthManager.is_authorized(context, provider)

        from mcp_agent.registry import is_provider_available
        registered = is_provider_available(context, provider)
        
        try:
            mcp_url = OAuthManager.get_mcp_url(context, provider)
        except Exception:
            mcp_url = None
        configured = bool(mcp_url) or registered
        actions = [self._build_tool(provider, fn, authorized, registered) for fn in funcs]
        return ProviderSpec(
            provider=provider,
            display_name=provider.capitalize(),
            authorized=authorized,
            registered=registered,
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
        registered: bool,
    ) -> ToolSpec:
        doc = inspect.getdoc(func) or ""
        description, param_docs = parse_action_docstring(doc)
        short_desc = short_description(description or doc, fallback=f"{provider}.{func.__name__}")
        signature = inspect.signature(func)
        parameters = []
        for param in signature.parameters.values():
            # CRITICAL: Filter out "self" and "context" to prevent TypeError
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
        available = authorized and registered
        if not authorized:
            reason = "unauthorized"
        elif not registered:
            reason = "not_registered"
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
    with _MANIFEST_CACHE_LOCK:
        entry = _MANIFEST_CACHE.get(key)
        needs_refresh = (
            refresh
            or entry is None
            or entry.manifest.fingerprint is None
        )

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
    """
    manifest = get_manifest(user_id=user_id)
    return ToolboxIndex.from_manifest(manifest)
