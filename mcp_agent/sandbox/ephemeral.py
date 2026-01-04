"""Ephemeral sandbox toolbox generator.

Creates a temporary ``sandbox_py`` package for each planner run so that
sandbox code can import provider helpers (``from sandbox_py.servers import gmail``)
without relying on a persisted toolbox directory on disk.
"""

from __future__ import annotations

import inspect
import shutil
import textwrap
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from mcp_agent.actions import get_provider_action_map
from mcp_agent.core.context import AgentContext
from mcp_agent.knowledge.utils import extract_call_tool_metadata
from mcp_agent.registry import get_available_providers, check_availability


def generate_ephemeral_toolbox(context: AgentContext, destination_dir: Path) -> None:
    """Generate a per-request ``sandbox_py`` package under ``destination_dir``.

    The stub modules mirror the available providers for the given user and proxy
    calls back through :mod:`mcp_agent.sandbox.runtime` so each sandbox plan can
    import helpers exactly as before (``from sandbox_py.servers import gmail``).
    """

    dest = destination_dir.resolve()
    base = dest / "sandbox_py"
    servers_dir = base / "servers"

    # Start from a clean slate each time.
    if base.exists():
        shutil.rmtree(base)
    servers_dir.mkdir(parents=True, exist_ok=True)

    # Generate core sandbox_py package modules
    _write_base_init(base)
    _write_helpers_module(base)
    _write_client_module(base / "client.py")

    provider_infos = get_available_providers(context)
    action_map = get_provider_action_map()

    generated: list[str] = []
    for info in sorted(provider_infos, key=lambda item: item["provider"]):
        if not info["authorized"]:
            continue
        funcs = action_map.get(info["provider"], ())
        if not funcs:
            continue

        available_funcs = [
            func
            for func in funcs
            if _is_tool_available(context, info["provider"], func.__name__)
        ]
        if not available_funcs:
            continue

        module_path = servers_dir / f"{info['provider']}.py"
        _write_provider_module(module_path, info["provider"], available_funcs)
        generated.append(info["provider"])

    _write_servers_init(servers_dir, generated)


def _is_tool_available(context: AgentContext, provider: str, tool: str) -> bool:
    available, _reason = check_availability(context, provider, tool)
    return available


def _write_base_init(base: Path) -> None:
    content = (
        "from . import client, servers, helpers\n"
        "from .helpers import safe_error_text, safe_timestamp_sort_key, is_tool_successful\n"
        "\n"
        "__all__ = [\n"
        "    \"client\",\n"
        "    \"servers\",\n"
        "    \"helpers\",\n"
        "    \"safe_error_text\",\n"
        "    \"safe_timestamp_sort_key\",\n"
        "    \"is_tool_successful\",\n"
        "]\n"
    )
    (base / "__init__.py").write_text(content, encoding="utf-8")


def _write_servers_init(servers_dir: Path, providers: Sequence[str]) -> None:
    lines = ["from __future__ import annotations", ""]
    for provider in sorted(providers):
        lines.append(f"from . import {provider}")
    lines.append("")
    exports = ", ".join(f'\"{name}\"' for name in sorted(providers))
    lines.append(f"__all__ = [{exports}]" if exports else "__all__ = []")
    (servers_dir / "__init__.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_helpers_module(base: Path) -> None:
    helpers_source = """\
\"\"\"Sandbox helper utilities exposed to generated plans.\"\"\"

from datetime import datetime


def safe_error_text(value):
    \"\"\"Return a safe string when concatenating provider errors.\"\"\"
    if not value:
        return ""
    return value if isinstance(value, str) else str(value)


def is_tool_successful(payload):
    \"\"\"Return True if a tool payload indicates success.\"\"\"
    if not isinstance(payload, dict):
        return False

    top_success = None
    if "successful" in payload:
        top_success = bool(payload.get("successful"))
    elif "successfull" in payload:
        top_success = bool(payload.get("successfull"))

    data = payload.get("data")
    nested_success = None
    nested_error = None
    if isinstance(data, dict):
        if "successful" in data:
            nested_success = bool(data.get("successful"))
        elif "successfull" in data:
            nested_success = bool(data.get("successfull"))
        if "error" in data:
            nested_error = data.get("error")

    # Nested failure should override any optimistic top-level flag.
    if nested_success is False:
        return False
    if nested_error not in (None, "", False) and nested_error is not None:
        return False

    top_error = payload.get("error")
    if top_error not in (None, "", False):
        return False

    if nested_success is True:
        return True
    if top_success is not None:
        return top_success
    return False


def safe_timestamp_sort_key(value):
    \"\"\"Convert provider timestamps (ints or ISO strings) into sortable ints.\"\"\"
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                cleaned = value.replace("Z", "+00:00")
                return int(datetime.fromisoformat(cleaned).timestamp())
            except Exception:
                return 0
    return 0
"""
    (base / "helpers.py").write_text(textwrap.dedent(helpers_source), encoding="utf-8")


def _write_client_module(path: Path) -> None:
    content = """from __future__ import annotations\n\nfrom mcp_agent.sandbox.runtime import (\n    ToolCallResult,\n    ToolCaller,\n    call_tool,\n    normalize_string_list,\n    redact_payload,\n    register_tool_caller,\n    sanitize_payload,\n)\n\n\n__all__ = [\n    \"ToolCallResult\",\n    \"ToolCaller\",\n    \"call_tool\",\n    \"register_tool_caller\",\n    \"sanitize_payload\",\n    \"normalize_string_list\",\n    \"redact_payload\",\n]\n"""
    path.write_text(content, encoding="utf-8")


def _write_provider_module(path: Path, provider: str, funcs: Iterable[Callable[..., Any]]) -> None:
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from mcp_agent.sandbox.runtime import ToolCallResult, call_tool, sanitize_payload",
        "",
        f"# Ephemeral stubs for provider '{provider}'.",
        "",
    ]

    for func in sorted(funcs, key=lambda f: f.__name__):
        lines.extend(_render_tool_function(provider, func))
        alias = _camel_case_alias(func.__name__)
        if alias:
            lines.append(f"{alias} = {func.__name__}")
            lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _render_tool_function(provider: str, func: Callable[..., Any]) -> list[str]:
    signature = inspect.signature(func)
    params = list(signature.parameters.values())
    # Drop the AgentContext parameter when present.
    body_params = params[1:] if params and params[0].name == "context" else params
    stub_signature = inspect.Signature(parameters=body_params)
    params_source = str(stub_signature)[1:-1].strip()
    param_text = params_source if params_source else ""

    _, mcp_tool_name = extract_call_tool_metadata(func)
    comment = f"    # Underlying MCP tool: {mcp_tool_name}" if mcp_tool_name else None

    lines = [f"async def {func.__name__}({param_text}) -> ToolCallResult:"]
    if comment:
        lines.append(comment)
    lines.append("    payload: dict[str, Any] = {}")

    for param in body_params:
        assignment = _payload_assignment(param)
        if assignment:
            lines.extend(assignment)

    lines.append("    sanitize_payload(payload)")
    lines.append(f"    return await call_tool('{provider}', '{func.__name__}', payload)")
    lines.append("")
    return lines


def _payload_assignment(param: inspect.Parameter) -> list[str] | None:
    name = param.name
    kind = param.kind

    if kind is inspect.Parameter.VAR_POSITIONAL:
        return [f"    if {name}:", f"        payload['{name}'] = list({name})"]
    if kind is inspect.Parameter.VAR_KEYWORD:
        return [f"    payload.update({name})"]

    if param.default is inspect.Signature.empty:
        return [f"    payload['{name}'] = {name}"]
    return [f"    if {name} is not None:", f"        payload['{name}'] = {name}"]


def _camel_case_alias(name: str) -> str | None:
    parts = name.split("_")
    if len(parts) <= 1:
        return None
    alias = parts[0] + "".join(part.capitalize() for part in parts[1:])
    if alias == name:
        return None
    return alias
