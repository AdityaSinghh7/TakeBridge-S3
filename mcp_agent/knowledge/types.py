"""Knowledge layer type definitions.

Combines runtime tool metadata (ToolSpec, ProviderSpec) and manual IO specifications
for documentation and probing utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from mcp_agent.types import ActionResponse


# ============================================================================
# Runtime tool metadata (used by planner and toolbox builder)
# ============================================================================


@dataclass
class ParameterSpec:
    """Structured representation of an MCP action parameter."""

    name: str
    kind: str
    required: bool
    has_default: bool = False
    annotation: Optional[str] = None
    default: Any = None
    default_repr: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "has_default": self.has_default,
        }
        if self.annotation is not None:
            data["annotation"] = self.annotation
        if self.has_default:
            data["default"] = self.default
            if self.default_repr is not None:
                data["default_repr"] = self.default_repr
        if self.description:
            data["description"] = self.description
        return data


@dataclass
class CompactToolDescriptor:
    """
    Ultra-compact, LLM-facing view of a toolbox tool.

    Designed to minimize context usage while providing exactly what the
    planner needs to write sandbox code and make tool calls.
    """

    tool_id: str                        # e.g., "gmail.gmail_search"
    server: str                         # e.g., "gmail" (needed for sandbox validation)
    description: str                    # Brief description of what the tool does
    signature: str                      # e.g., "gmail.gmail_search(query, max_results=20)"
    input_params: Dict[str, str]        # {"query": "str (required)", "max_results": "int (optional, default=20)"}
    output_fields: List[str]            # ["messages[].id", "messages[].subject", ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_id": self.tool_id,
            "server": self.server,
            "description": self.description,
            "signature": self.signature,
            "input_params": self.input_params,
            "output_fields": self.output_fields,
        }


@dataclass
class LLMToolDescriptor:
    """
    Legacy LLM-facing view of a toolbox tool.

    DEPRECATED: Use CompactToolDescriptor instead for new code.
    This is kept for backwards compatibility with existing search code.
    """

    provider: str
    server: str
    module: str
    function: str
    tool_id: str

    call_signature: str
    description: str

    input_params_pretty: List[str]
    output_schema_pretty: List[str]

    input_params: Dict[str, Any]
    output_schema: Dict[str, Any]

    score: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "server": self.server,
            "module": self.module,
            "function": self.function,
            "tool_id": self.tool_id,
            "call_signature": self.call_signature,
            "description": self.description,
            "input_params_pretty": self.input_params_pretty,
            "output_schema_pretty": self.output_schema_pretty,
            "input_params": self.input_params,
            "output_schema": self.output_schema,
            "score": self.score,
        }


@dataclass
class ToolSpec:
    """Metadata describing a single MCP action wrapper."""

    provider: str
    name: str
    description: str
    short_description: str
    docstring: str
    python_name: str
    python_signature: str
    parameters: List[ParameterSpec] = field(default_factory=list)
    mcp_tool_name: Optional[str] = None
    oauth_provider: Optional[str] = None
    oauth_required: bool = True
    available: bool = False
    availability_reason: Optional[str] = None
    source_path: Optional[str] = None
    source_line: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    returns: Optional[str] = None
    structured_params: List[str] = field(default_factory=list)
    list_params: Dict[str, str] = field(default_factory=dict)
    primary_param: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    output_schema_pretty: Optional[List[str]] = None

    @property
    def tool_id(self) -> str:
        """Stable identifier used by the planner (e.g. 'gmail.gmail_search')."""
        return f"{self.provider}.{self.name}"

    @property
    def server(self) -> str:
        """Logical server name; today this matches the provider id."""
        return self.provider

    @property
    def py_module(self) -> str:
        """Python module path for the sandbox helper."""
        return f"sandbox_py.servers.{self.provider}"

    @property
    def py_name(self) -> str:
        """Python function name exposed by the sandbox helper."""
        return self.python_name

    @property
    def params(self) -> Dict[str, Dict[str, Any]]:
        """Structured parameter metadata grouped into required/optional."""
        required: Dict[str, Any] = {}
        optional: Dict[str, Any] = {}
        for param in self.parameters:
            target = required if param.required else optional
            target[param.name] = param.annotation or "Any"
        return {"required": required, "optional": optional}

    def to_compact_descriptor(self) -> CompactToolDescriptor:
        """
        Convert this ToolSpec into an ultra-compact CompactToolDescriptor.

        This method generates a minimal representation optimized for LLM context,
        containing only essential information needed for sandbox code generation
        and tool invocation.
        """
        # Build compact signature with minimal formatting
        param_parts: List[str] = []
        for param in self.parameters:
            if param.has_default:
                if param.default_repr is not None:
                    param_parts.append(f"{param.name}={param.default_repr}")
                else:
                    param_parts.append(f"{param.name}={repr(param.default)}")
            else:
                param_parts.append(param.name)

        signature = f"{self.server}.{self.py_name}({', '.join(param_parts)})"

        # Build readable input_params dict
        input_params: Dict[str, str] = {}
        for param in self.parameters:
            param_type = param.annotation or "Any"
            if param.required:
                label = f"{param_type} (required)"
            else:
                default_val = param.default_repr if param.default_repr is not None else repr(param.default)
                label = f"{param_type} (optional, default={default_val})"
            if param.description:
                label = f"{label} - {param.description.strip()}"
            input_params[param.name] = label

        # Get output_fields from schema
        from mcp_agent.knowledge.utils import flatten_schema_fields

        output_fields = flatten_schema_fields(
            self.output_schema,
            max_depth=3,
            max_fields=30
        ) if self.output_schema else []

        return CompactToolDescriptor(
            tool_id=self.tool_id,
            server=self.server,
            description=self.short_description or self.description or "",
            signature=signature,
            input_params=input_params,
            output_fields=output_fields,
        )

    def to_llm_descriptor(self, *, score: float = 0.0) -> LLMToolDescriptor:
        """
        Convert this ToolSpec into an LLMToolDescriptor.

        Keeps internal richness on ToolSpec while exposing a clean, single-level
        view for the planner and sandbox validation.
        """
        required_params: List[Dict[str, Any]] = []
        optional_params: List[Dict[str, Any]] = []
        for param in self.parameters:
            info: Dict[str, Any] = {
                "name": param.name,
                "type": param.annotation or "Any",
            }
            if param.has_default:
                default_value: Any
                if param.default_repr is not None:
                    default_value = param.default_repr
                else:
                    default_value = param.default
                info["default"] = default_value
            if param.required:
                required_params.append(info)
            else:
                optional_params.append(info)

        input_params = {
            "required": required_params,
            "optional": optional_params,
        }

        param_segments: List[str] = []
        for param in self.parameters:
            kind = param.kind
            prefix = ""
            if kind == "var_keyword":
                prefix = "**"
            elif kind == "var_positional":
                prefix = "*"
            annotation = param.annotation or "Any"
            segment = f"{prefix}{param.name}: {annotation}"
            if param.has_default:
                if param.default_repr is not None:
                    default_str = param.default_repr
                else:
                    default_str = repr(param.default)
                segment = f"{segment} = {default_str}"
            param_segments.append(segment)

        call_signature = f"{self.server}.{self.py_name}({', '.join(param_segments)})"

        input_lines: List[str] = [f"Call: {call_signature}"]
        if required_params:
            input_lines.append("")
            input_lines.append("Required params:")
            for rp in required_params:
                line = f"  - {rp['name']}: {rp['type']}"
                input_lines.append(line)
        if optional_params:
            input_lines.append("")
            input_lines.append("Optional params:")
            for op in optional_params:
                line = f"  - {op['name']}: {op['type']}"
                if "default" in op:
                    line = f"{line} = {op['default']}"
                input_lines.append(line)

        output_lines: List[str] = list(self.output_schema_pretty) if self.output_schema_pretty else []

        return LLMToolDescriptor(
            provider=self.provider,
            server=self.server,
            module=self.py_module,
            function=self.py_name,
            tool_id=self.tool_id,
            call_signature=call_signature,
            description=self.short_description or self.description or "",
            input_params_pretty=input_lines,
            output_schema_pretty=output_lines,
            input_params=input_params,
            output_schema=self.output_schema or {},
            score=score,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "provider": self.provider,
            "name": self.name,
            "description": self.description,
            "short_description": self.short_description,
            "docstring": self.docstring,
            "python_name": self.python_name,
            "python_signature": self.python_signature,
            "parameters": [param.to_dict() for param in self.parameters],
            "oauth_required": self.oauth_required,
            "available": self.available,
        }
        if self.mcp_tool_name:
            data["mcp_tool_name"] = self.mcp_tool_name
        if self.oauth_provider:
            data["oauth_provider"] = self.oauth_provider
        if self.availability_reason:
            data["availability_reason"] = self.availability_reason
        if self.source_path:
            data["source_path"] = self.source_path
        if self.source_line is not None:
            data["source_line"] = self.source_line
        if self.tags:
            data["tags"] = self.tags
        if self.returns:
            data["returns"] = self.returns
        if self.structured_params:
            data["structured_params"] = sorted(self.structured_params)
        if self.list_params:
            data["list_params"] = dict(self.list_params)
        if self.primary_param:
            data["primary_param"] = self.primary_param
        if self.metadata:
            data["metadata"] = self.metadata
        if self.output_schema:
            data["output_schema"] = self.output_schema
        if self.output_schema_pretty:
            data["output_schema_pretty"] = self.output_schema_pretty
        return data


@dataclass
class ProviderSpec:
    """Provider-level metadata (authorization + tool catalog).

    Note: The 'registered' field was removed as it was redundant with 'authorized'.
    Both inventory view and search now use the same authorization logic from
    OAuthManager.auth_status().
    """

    provider: str
    display_name: str
    authorized: bool
    configured: bool
    mcp_url: Optional[str]
    actions: List[ToolSpec] = field(default_factory=list)
    last_refreshed: Optional[str] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "display_name": self.display_name,
            "authorized": self.authorized,
            "configured": self.configured,
            "mcp_url": self.mcp_url,
            "tool_count": len(self.actions),
            "all_actions": [tool.name for tool in self.actions],
            "available_tools": [tool.name for tool in self.actions if tool.available],
        }

    @property
    def available_tools(self) -> List[str]:
        """Convenience mirror of summary()['available_tools'] for internal callers."""
        return [tool.name for tool in self.actions if tool.available]

    def to_dict(self, include_tools: bool = True) -> Dict[str, Any]:
        data = self.summary()
        data["tool_count"] = len(self.actions)
        if self.last_refreshed:
            data["last_refreshed"] = self.last_refreshed
        if include_tools:
            data["actions"] = [tool.to_dict() for tool in self.actions]
        else:
            data["actions"] = [tool.name for tool in self.actions]
        return data


@dataclass
class ToolboxManifest:
    """High-level manifest describing all discovered MCP actions."""

    user_id: str
    generated_at: str
    registry_version: int
    fingerprint: str
    providers: List[ProviderSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "generated_at": self.generated_at,
            "registry_version": self.registry_version,
            "fingerprint": self.fingerprint,
            "providers": [provider.to_dict() for provider in self.providers],
        }

    def provider_map(self) -> Dict[str, ProviderSpec]:
        return {provider.provider: provider for provider in self.providers}

    def all_tools(self) -> List[ToolSpec]:
        tools: List[ToolSpec] = []
        for provider in self.providers:
            tools.extend(provider.actions)
        return tools


# ============================================================================
# Manual IO specifications for documentation and probing utilities
# ============================================================================


@dataclass
class InputParamSpec:
    """Manual description of a single tool input parameter."""

    name: str
    type: str  # e.g. "string", "int", "boolean", "list[string]"
    required: bool
    description: str = ""
    default: Any | None = None
    enum: List[Any] | None = None


@dataclass
class ToolInputSpec:
    """Collection of input parameters for a tool."""

    params: List[InputParamSpec] = field(default_factory=list)

    def pretty(self) -> str:
        lines: List[str] = ["Input parameters:"]
        for p in self.params:
            header = f"- {p.name}: {p.type} "
            header += "(required)" if p.required else "(optional"
            if p.default is not None:
                header += f", default={p.default!r}"
            header += ")"
            lines.append(header)
            if p.description:
                lines.append(f"  {p.description}")
            if p.enum:
                enum_values = ", ".join(map(repr, p.enum))
                lines.append(f"  Allowed values: {enum_values}")
        return "\n".join(lines)


@dataclass
class ToolOutputSpec:
    """
    JSON-schema-like shapes for the `data` field in successful and error cases.

    These are meant for documentation and planner prompts rather than strict
    runtime validation.
    """

    data_schema_success: dict[str, Any] | None = None
    data_schema_error: dict[str, Any] | None = None
    pretty_success: str = ""
    pretty_error: str = ""


@dataclass
class IoToolSpec:
    """
    Canonical, manual description of a tool for registry and probing utilities.

    This is independent of the introspection-based ToolSpec used by the
    toolbox builder and is not wired into planner discovery by default.
    """

    provider: str  # "gmail", "slack", ...
    tool_name: str  # "gmail_search"
    python_name: str  # "gmail_search"
    python_signature: str  # "await gmail.gmail_search(query: str, ...)"
    description: str

    input_spec: ToolInputSpec
    output_spec: ToolOutputSpec = field(default_factory=ToolOutputSpec)

    # Optional: direct pointer to the Python wrapper.
    func: Callable[..., ActionResponse] | None = None
