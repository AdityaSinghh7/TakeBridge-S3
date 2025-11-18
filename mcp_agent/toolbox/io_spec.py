from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from .types import ActionResponse

"""
Manual IO specifications used by probing and documentation utilities.

These specs are independent of the runtime toolbox/index used by the planner
and are not wired into planner discovery by default.
"""


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

# Backwards-compat alias for older scripts; prefer IoToolSpec in new code.
ToolSpec = IoToolSpec
