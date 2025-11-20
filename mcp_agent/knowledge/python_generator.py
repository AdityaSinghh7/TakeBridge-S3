"""Python sandbox code generator for MCP tools.

Migrated from toolbox/python_generator.py - generates Python stubs for sandbox execution.
The context parameter is automatically filtered out by the builder, so generated
signatures will not include it.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set

from mcp_agent.toolbox.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
from mcp_agent.toolbox.utils import ensure_dir, safe_filename, to_camel_case, write_text_if_changed


class ToolWriteResult(NamedTuple):
    module: str
    exports: List[str]
    changed: bool


class PythonGenerator:
    """Generate Python sandbox modules that mirror available MCP tools."""

    def __init__(self, manifest: ToolboxManifest, base_dir: Path) -> None:
        self.manifest = manifest
        self.base_dir = Path(base_dir)
        self.sandbox_dir = self.base_dir / "sandbox_py"
        self.servers_dir = self.sandbox_dir / "servers"

    def write(self) -> Dict[str, int]:
        stats = {"py_files": 0}
        stats["py_files"] += int(self._write_package_init())
        stats["py_files"] += int(self._write_client())
        stats["py_files"] += int(self._write_servers_init())
        for provider in sorted(self.manifest.providers, key=lambda prov: prov.provider):
            stats["py_files"] += self._write_provider(provider)
        return stats

    def _write_package_init(self) -> bool:
        ensure_dir(self.sandbox_dir)
        path = self.sandbox_dir / "__init__.py"
        content = textwrap.dedent(
            """\
            \"\"\"Generated sandbox helpers for MCP tool execution.\"\"\"

            from .client import (
                ToolCallResult,
                ToolCaller,
                call_tool,
                register_tool_caller,
                sanitize_payload,
                serialize_structured_param,
                normalize_string_list,
                merge_recipient_lists,
            )

            __all__ = [
                "ToolCallResult",
                "ToolCaller",
                "call_tool",
                "register_tool_caller",
                "sanitize_payload",
                "serialize_structured_param",
                "normalize_string_list",
                "merge_recipient_lists",
            ]
            """
        )
        return write_text_if_changed(path, content)

    def _write_client(self) -> bool:
        path = self.sandbox_dir / "client.py"
        return write_text_if_changed(path, CLIENT_TEMPLATE)

    def _write_servers_init(self) -> bool:
        ensure_dir(self.servers_dir)
        provider_modules = [
            self._provider_module_name(provider.provider)
            for provider in sorted(self.manifest.providers, key=lambda prov: prov.provider)
        ]
        lines: List[str] = []
        for module in provider_modules:
            lines.append(f"from . import {module}")
        lines.append("")
        exports = ", ".join(f'"{module}"' for module in provider_modules)
        lines.append(f"__all__ = [{exports}]")
        return write_text_if_changed(self.servers_dir / "__init__.py", "\n".join(lines))

    def _write_provider(self, provider: ProviderSpec) -> int:
        provider_dir = self.servers_dir / self._provider_module_name(provider.provider)
        ensure_dir(provider_dir)
        total = 0
        tool_results: List[tuple[ToolSpec, ToolWriteResult]] = []
        for tool in sorted(provider.actions, key=lambda action: action.name):
            writer = get_tool_writer(self, provider, tool)
            result = writer.write(provider_dir)
            tool_results.append((tool, result))
            total += int(result.changed)
        provider_init_lines: List[str] = []
        seen_exports: Set[str] = set()
        for tool, result in tool_results:
            for export in result.exports:
                provider_init_lines.append(f"from .{result.module} import {export}")
                seen_exports.add(export)
        provider_init_lines.append("")
        exported_list = ", ".join(f'"{name}"' for name in sorted(seen_exports))
        provider_init_lines.append(f"__all__ = [{exported_list}]")
        if write_text_if_changed(provider_dir / "__init__.py", "\n".join(provider_init_lines)):
            total += 1
        return total

    @staticmethod
    def _provider_module_name(provider: str) -> str:
        return provider.replace("-", "_")


class PythonParameter:
    def __init__(
        self,
        spec: ParameterSpec,
        *,
        structured: bool,
        list_normalizer: Optional[str],
    ) -> None:
        self.spec = spec
        self.structured = structured
        self.list_normalizer = list_normalizer

    @property
    def annotation(self) -> str:
        return self.spec.annotation or "Any"

    def signature_fragment(self) -> str:
        name = self.spec.name
        if self.spec.kind == "var_positional":
            return f"*{name}"
        if self.spec.kind == "var_keyword":
            return f"**{name}"
        default = ""
        if self.spec.has_default:
            if self.spec.default is None:
                default = " = None"
            else:
                default = f" = {repr(self.spec.default)}"
        return f"{name}: {self.annotation}{default}"

    def assignment_lines(self) -> List[str]:
        lines: List[str] = []
        target = f'payload["{self.spec.name}"]'
        name = self.spec.name
        if self.structured:
            temp = f"{name}_serialized"
            lines.append(f"    {temp} = serialize_structured_param({name})")
            lines.append(f"    if {temp} is not None:")
            lines.append(f"        {target} = {temp}")
            return lines
        if self.list_normalizer:
            temp = f"{name}_list"
            lines.append(f"    {temp} = normalize_string_list({name})")
            lines.append(f"    if {temp}:")
            lines.append(f"        {target} = {temp}")
            return lines
        if hint_is_boolean(self.annotation):
            lines.append(f"    if {name} is not None:")
            lines.append(f"        {target} = bool({name})")
            return lines
        if self.spec.required:
            lines.append(f"    {target} = {name}")
        else:
            lines.append(f"    if {name} is not None:")
            lines.append(f"        {target} = {name}")
        return lines


class BaseToolWriter:
    def __init__(self, generator: PythonGenerator, provider: ProviderSpec, tool: ToolSpec) -> None:
        self.generator = generator
        self.provider = provider
        self.tool = tool
        self.module_name = safe_filename(tool.name)
        self.function_name = tool.name
        self.camel_alias = to_camel_case(self.function_name)

    def helper_imports(self) -> Set[str]:
        helpers: Set[str] = {"call_tool", "sanitize_payload", "ToolCallResult"}
        if self.tool.structured_params:
            helpers.add("serialize_structured_param")
        if self.tool.list_params:
            helpers.add("normalize_string_list")
        return helpers

    def render(self) -> str:
        imports = ", ".join(sorted(self.helper_imports()))
        lines: List[str] = []
        lines.append("from __future__ import annotations")
        lines.append("")
        lines.append("from typing import Any")
        lines.append("")
        lines.append(f"from ...client import {imports}")
        lines.append("")
        lines.append(self._docstring_block())
        signature = self._function_signature()
        lines.append(f"async def {self.function_name}{signature} -> ToolCallResult[Any]:")
        body = self._render_body()
        lines.extend(body)
        lines.append("")
        lines.extend(self._alias_lines())
        return "\n".join(lines)

    def _function_signature(self) -> str:
        # NOTE: self.tool.parameters already has "context" filtered out by builder
        params = [
            PythonParameter(
                param,
                structured=param.name in self.tool.structured_params,
                list_normalizer=self.tool.list_params.get(param.name)
            )
            for param in self.tool.parameters
        ]
        fragments: List[str] = []
        inserted_kw_marker = False
        for param in params:
            kind = param.spec.kind
            if kind == "keyword_only" and not inserted_kw_marker:
                fragments.append("*")
                inserted_kw_marker = True
            fragments.append(param.signature_fragment())
        joined = ", ".join(fragments)
        if joined:
            return f"({joined})"
        return "()"

    def _docstring_block(self) -> str:
        description = self.tool.description or self.tool.short_description
        header = description.strip() if description else f"{self.provider.display_name} tool."
        lines = ['"""', header, "", f"Provider: {self.provider.display_name}", f"Tool: {self.tool.mcp_tool_name or ''}"]
        if self.tool.parameters:
            lines.append("")
            lines.append("Args:")
            for param in self.tool.parameters:
                desc = (param.description or "").strip()
                annotation = param.annotation or "Any"
                lines.append(f"    {param.name} ({annotation}): {desc}".rstrip())
        lines.append('"""')
        return "\n".join(lines)

    def _render_body(self) -> List[str]:
        lines: List[str] = ["    payload: dict[str, Any] = {}"]
        for param in self.tool.parameters:
            model = PythonParameter(
                param,
                structured=param.name in self.tool.structured_params,
                list_normalizer=self.tool.list_params.get(param.name),
            )
            lines.extend(model.assignment_lines())
        lines.append("    sanitize_payload(payload)")
        provider_name = self.tool.provider
        tool_name = self.tool.mcp_tool_name or self.tool.name.upper()
        lines.append(f"    return await call_tool('{provider_name}', '{tool_name}', payload)")
        return lines

    def _alias_lines(self) -> List[str]:
        aliases = []
        if self.camel_alias != self.function_name:
            aliases.append(f"{self.camel_alias} = {self.function_name}")
        return aliases

    def export_names(self) -> List[str]:
        names = [self.function_name]
        if self.camel_alias != self.function_name:
            names.append(self.camel_alias)
        return names

    def write(self, provider_dir: Path) -> ToolWriteResult:
        path = provider_dir / f"{self.module_name}.py"
        changed = write_text_if_changed(path, self.render())
        return ToolWriteResult(module=self.module_name, exports=self.export_names(), changed=changed)


class GmailSendEmailWriter(BaseToolWriter):
    def helper_imports(self) -> Set[str]:
        helpers = super().helper_imports()
        helpers.add("merge_recipient_lists")
        return helpers

    def _render_body(self) -> List[str]:
        lines = [
            "    to_list = normalize_string_list(to) or []",
            "    if not to_list:",
            "        raise ValueError('gmail_send_email requires at least one recipient in `to`.')",
            "    primary_recipient = to_list[0]",
            "    extra_recipients = to_list[1:]",
            "    cc_list = merge_recipient_lists(cc, extra_recipients)",
            "    bcc_list = normalize_string_list(bcc)",
            "    payload: dict[str, Any] = {",
            "        'recipient_email': primary_recipient,",
            "        'subject': subject,",
            "        'body': body,",
            "        'is_html': bool(is_html),",
            "    }",
            "    if cc_list:",
            "        payload['cc'] = cc_list",
            "    if bcc_list:",
            "        payload['bcc'] = bcc_list",
            "    if thread_id is not None:",
            "        payload['thread_id'] = thread_id",
            "    sanitize_payload(payload)",
            "    return await call_tool('gmail', 'GMAIL_SEND_EMAIL', payload)",
        ]
        return lines


def get_tool_writer(generator: PythonGenerator, provider: ProviderSpec, tool: ToolSpec) -> BaseToolWriter:
    if provider.provider == "gmail" and tool.name == "gmail_send_email":
        return GmailSendEmailWriter(generator, provider, tool)
    return BaseToolWriter(generator, provider, tool)


def hint_is_boolean(annotation: Optional[str]) -> bool:
    if not annotation:
        return False
    return "bool" in annotation.lower()


CLIENT_TEMPLATE = textwrap.dedent(
    """\
    from __future__ import annotations

    import asyncio
    import json
    import logging
    from typing import Any, Awaitable, Callable, Dict, Iterable, MutableMapping, Optional, Protocol, Sequence, TypedDict

    logger = logging.getLogger(__name__)


    class ToolCallResult(TypedDict, total=False):
        successful: bool
        data: Any
        error: Any
        logs: Any


    class ToolCaller(Protocol):
        def __call__(self, provider: str, tool: str, payload: Dict[str, Any]) -> Awaitable[ToolCallResult] | ToolCallResult:
            ...


    _REGISTERED_CALLER: ToolCaller | None = None
    _DEFAULT_REDACT_KEYS = ("token", "authorization", "password", "api_key", "secret")


    def register_tool_caller(caller: ToolCaller) -> None:
        \"\"\"Bind the sandbox runtime to an MCP bridge callable.\"\"\"
        global _REGISTERED_CALLER
        _REGISTERED_CALLER = caller


    async def call_tool(
        provider: str,
        tool: str,
        payload: Dict[str, Any],
        *,
        retries: int = 2,
        retry_delay: float = 0.1,
    ) -> ToolCallResult:
        \"\"\"Invoke an MCP tool via the registered bridge with basic retries.\"\"\"
        if _REGISTERED_CALLER is None:
            raise RuntimeError("No sandbox tool caller registered. Call register_tool_caller() first.")
        sanitized = sanitize_payload(dict(payload))
        redacted = redact_payload(dict(sanitized), _DEFAULT_REDACT_KEYS)
        attempt = 0
        last_error: Exception | None = None
        while attempt <= retries:
            try:
                result = _REGISTERED_CALLER(provider, tool, sanitized)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as exc:  # pragma: no cover - retry logic
                last_error = exc
                logger.warning(
                    "tool call %s.%s failed (attempt %s/%s): %s",
                    provider,
                    tool,
                    attempt + 1,
                    retries + 1,
                    exc,
                )
                if attempt >= retries:
                    exc.payload = redacted  # type: ignore[attr-defined]
                    raise
                await asyncio.sleep(retry_delay * (attempt + 1))
            finally:
                attempt += 1
        if last_error:
            raise last_error
        raise RuntimeError("call_tool failed without raising an explicit error.")


    def sanitize_payload(payload: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        \"\"\"Remove keys whose value is None to keep payloads compact.\"\"\"
        for key in list(payload.keys()):
            if payload[key] is None:
                payload.pop(key)
        return payload


    StructuredData = Any
    StringListInput = Any


    def serialize_structured_param(value: StructuredData) -> str | None:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value)
        except Exception as exc:  # pragma: no cover - serialization errors
            raise ValueError(f"Failed to serialize structured payload: {exc}") from exc


    def normalize_string_list(value: StringListInput) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            candidates = value.replace(";", ",").split(",")
            return [entry.strip() for entry in candidates if entry.strip()]
        if isinstance(value, Iterable):
            cleaned = []
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    cleaned.append(entry.strip())
            return cleaned
        return [str(value)]


    def merge_recipient_lists(base: StringListInput, extras: Sequence[str] | None = None) -> list[str]:
        combined = normalize_string_list(base)
        if extras:
            combined.extend(extra for extra in extras if extra)
        deduped: list[str] = []
        seen = set()
        for entry in combined:
            lowered = entry.lower()
            if lowered not in seen:
                deduped.append(entry)
                seen.add(lowered)
        return deduped


    def redact_payload(payload: Dict[str, Any], sensitive_keys: Sequence[str]) -> Dict[str, Any]:
        lowered = {key.lower() for key in sensitive_keys}
        clone: Dict[str, Any] = {}
        for key, value in payload.items():
            clone[key] = "[REDACTED]" if key.lower() in lowered else value
        return clone
    """
)

