from __future__ import annotations

from typing import Any, Dict, List, Literal

from .builder import get_manifest
from .models import ProviderSpec, ToolSpec
from .utils import safe_filename

DetailLevel = Literal["names", "summary", "full"]


def list_providers(user_id: str | None = None) -> List[Dict[str, Any]]:
    manifest = get_manifest(user_id=user_id, persist=False)
    providers = []
    for provider in manifest.providers:
        entry = provider.summary()
        entry["path"] = f"providers/{provider.provider}/provider.json"
        providers.append(entry)
    return providers


def search_tools(
    query: str | None = None,
    *,
    provider: str | None = None,
    detail_level: DetailLevel = "summary",
    limit: int = 20,
    user_id: str | None = None,
) -> List[Dict[str, Any]]:
    norm_query = _normalize_query(query)
    provider_filter = provider.lower().strip() if provider else None
    manifest = get_manifest(user_id=user_id, persist=False)
    matches: List[tuple[int, ProviderSpec, ToolSpec]] = []

    for prov in manifest.providers:
        if provider_filter and prov.provider.lower() != provider_filter:
            continue
        for tool in prov.actions:
            score = _score_tool(tool, norm_query)
            if norm_query.terms and score == 0:
                continue
            matches.append((score, prov, tool))

    matches.sort(key=lambda item: (-item[0], item[1].provider, item[2].name))
    if limit and limit > 0:
        matches = matches[:limit]

    formatter = _result_formatter(detail_level)
    return [formatter(score, prov, tool) for score, prov, tool in matches]


class _Query:
    def __init__(self, raw: str | None) -> None:
        text = (raw or "").strip().lower()
        self.raw = text
        self.terms = [term for term in text.split() if term]


def _normalize_query(query: str | None) -> _Query:
    return _Query(query)


def _score_tool(tool: ToolSpec, query: _Query) -> int:
    if not query.terms:
        return 2 if tool.available else 1
    score = 0
    haystacks = {
        "name": tool.name.lower(),
        "provider": tool.provider.lower(),
        "description": (tool.description or "").lower(),
        "doc": (tool.docstring or "").lower(),
        "mcp_tool": (tool.mcp_tool_name or "").lower(),
    }
    param_names = [param.name.lower() for param in tool.parameters]
    for term in query.terms:
        if term in haystacks["name"]:
            score += 5
        if term in haystacks["provider"]:
            score += 3
        if term in haystacks["description"]:
            score += 2
        if term in haystacks["doc"]:
            score += 1
        if any(term in name for name in param_names):
            score += 1
        if term in haystacks["mcp_tool"]:
            score += 2
    return score


def _result_formatter(detail_level: DetailLevel):
    if detail_level == "names":
        return _format_names
    if detail_level == "summary":
        return _format_summary
    if detail_level == "full":
        return _format_full
    raise ValueError(f"Unsupported detail level '{detail_level}'.")


def _format_names(score: int, provider: ProviderSpec, tool: ToolSpec) -> Dict[str, Any]:
    return {
        "provider": provider.provider,
        "tool": tool.name,
        "qualified_name": f"{provider.provider}.{tool.name}",
        "available": tool.available,
        "score": score,
    }


def _format_summary(score: int, provider: ProviderSpec, tool: ToolSpec) -> Dict[str, Any]:
    return {
        "provider": provider.provider,
        "tool": tool.name,
        "short_description": tool.short_description,
        "available": tool.available,
        "availability_reason": tool.availability_reason,
        "parameters": [param.name for param in tool.parameters],
        "mcp_tool_name": tool.mcp_tool_name,
        "score": score,
        "path": f"providers/{provider.provider}/tools/{safe_filename(tool.name)}.json",
    }


def _format_full(score: int, provider: ProviderSpec, tool: ToolSpec) -> Dict[str, Any]:
    payload = tool.to_dict()
    payload["provider_status"] = provider.summary()
    payload["score"] = score
    payload["path"] = f"providers/{provider.provider}/tools/{safe_filename(tool.name)}.json"
    return payload
