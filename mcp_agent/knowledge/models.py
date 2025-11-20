from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
class LLMToolDescriptor:
    """
    Compact, LLM-facing view of a toolbox tool.

    This is the only shape the planner should consume from `search_tools(...)`.
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
    output_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema_pretty: List[str] = field(default_factory=list)

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

        if self.output_schema_pretty:
            output_lines = list(self.output_schema_pretty)
        else:
            output_lines = [
                "Canonical wrapper: { success: bool, data: dict, error: str | null }",
                "",
                "data: <schema not documented; TODO: replace with real Composio-compatible payload schema>",
            ]

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
    """Provider-level metadata (authorization + tool catalog)."""

    provider: str
    display_name: str
    authorized: bool
    registered: bool
    configured: bool
    mcp_url: Optional[str]
    actions: List[ToolSpec] = field(default_factory=list)
    last_refreshed: Optional[str] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "display_name": self.display_name,
            "authorized": self.authorized,
            "registered": self.registered,
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

