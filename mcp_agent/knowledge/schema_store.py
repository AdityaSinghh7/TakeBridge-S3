from __future__ import annotations

import json
from pathlib import Path
import os
from typing import Any, Dict

from .io_spec import ToolOutputSpec
from .registry import get_tool_spec


def _default_schema_path() -> Path:
    """
    Resolve the default path for generated tool output schemas.

    When TB_TOOL_OUTPUT_SCHEMAS_PATH is set, that path is used instead of the
    repo-root default. This makes it easy for tests to point at a fixture file.
    """
    env_path = os.getenv("TB_TOOL_OUTPUT_SCHEMAS_PATH")
    if env_path:
        return Path(env_path)
    # Assume the generated schema file lives at the repo root next to scripts/.
    # This resolves two levels up from this file (../..) and appends the filename.
    return Path(__file__).resolve().parents[2] / "tool_output_schemas.generated.json"


def _pretty_from_schema(schema: Dict[str, Any]) -> str:
    """Create a short human-readable description from a JSON-like schema."""
    props = schema.get("properties") or {}
    lines = ["data keys:"]
    for name in sorted(props.keys()):
        t = props[name].get("type", "unknown")
        lines.append(f"- {name}: {t}")
    return "\n".join(lines)


def load_output_schemas(path: Path | None = None) -> None:
    """
    Merge generated output schemas into registered IoToolSpecs.

    The JSON is expected to have the structure:
      {
        "provider.tool_name": {
          "success": { ... },
          "error": { ... }
        },
        ...
      }
    """
    schema_path = path or _default_schema_path()
    if not schema_path.exists():
        return

    data: Dict[str, Dict[str, Any]] = json.loads(schema_path.read_text(encoding="utf-8"))

    for key, entry in data.items():
        try:
            provider, tool_name = key.split(".", 1)
        except ValueError:
            continue

        spec = get_tool_spec(provider, tool_name)
        if spec is None:
            continue

        out_spec: ToolOutputSpec = spec.output_spec or ToolOutputSpec()

        success_schema = entry.get("success")
        error_schema = entry.get("error")

        if success_schema:
            out_spec.data_schema_success = success_schema
            out_spec.pretty_success = _pretty_from_schema(success_schema)
        if error_schema:
            out_spec.data_schema_error = error_schema
            out_spec.pretty_error = _pretty_from_schema(error_schema)

        spec.output_spec = out_spec

