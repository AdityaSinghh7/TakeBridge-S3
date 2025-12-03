from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return _REPO_ROOT


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_action_docstring(doc: str | None) -> tuple[str, Dict[str, str]]:
    """Extract a description plus per-parameter docs from a structured docstring."""
    if not doc:
        return "", {}
    cleaned = inspect.cleandoc(doc)
    description_lines: list[str] = []
    param_docs: Dict[str, str] = {}
    section = None
    current_param: Optional[str] = None

    for raw in cleaned.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in {"description:", "desc:"}:
            section = "description"
            current_param = None
            continue
        if lowered in {"args:", "arguments:", "parameters:"}:
            section = "args"
            current_param = None
            continue
        if section == "args":
            if ":" in line:
                name, rest = line.split(":", 1)
                current_param = name.strip()
                param_docs[current_param] = rest.strip()
            elif current_param:
                param_docs[current_param] = f"{param_docs.get(current_param, '')} {line}".strip()
            continue
        description_lines.append(line)

    description = " ".join(description_lines).strip()
    return description, param_docs


def short_description(text: str, *, fallback: str = "") -> str:
    snippet = (text or "").strip()
    if not snippet:
        return fallback
    for delimiter in (". ", " - ", ": "):
        if delimiter in snippet:
            return snippet.split(delimiter, 1)[0].strip().rstrip(".")
    return snippet.splitlines()[0].strip().rstrip(".")


def format_annotation(annotation: Any) -> str | None:
    if annotation is inspect._empty:
        return None
    try:
        value = getattr(annotation, "__name__", None)
        if value:
            return value
        return str(annotation).replace("typing.", "")
    except Exception:
        return repr(annotation)


def serialize_default(value: Any) -> tuple[Any | None, str | None]:
    if value is inspect._empty:
        return None, None
    try:
        json.dumps(value)
        return value, None
    except TypeError:
        return None, repr(value)


def action_signature(func: Any) -> str:
    try:
        sig = inspect.signature(func)
        return f"{func.__name__}{sig}"
    except (TypeError, ValueError):
        return func.__name__


def _call_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def relative_source_path(func: Any) -> tuple[str | None, int | None]:
    try:
        src_file = inspect.getsourcefile(func) or inspect.getfile(func)
        if not src_file:
            return None, None
        path = Path(src_file).resolve()
        rel = path
        try:
            rel = path.relative_to(repo_root())
        except ValueError:
            pass
        _, line = inspect.getsourcelines(func)
        return rel.as_posix(), line
    except (OSError, TypeError):
        return None, None


def extract_call_tool_metadata(func: Any) -> tuple[Optional[str], Optional[str]]:
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return None, None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, None

    provider: Optional[str] = None
    tool_name: Optional[str] = None

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._string_assignments: Dict[str, str] = {}

        def visit_Assign(self, node: ast.Assign) -> Any:
            target = node.targets[0] if node.targets else None
            if (
                isinstance(target, ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                self._string_assignments[target.id] = node.value.value
            self.generic_visit(node)

        def _string_value(self, node: ast.AST | None) -> Optional[str]:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.Name):
                return self._string_assignments.get(node.id)
            return None

        def visit_Call(self, node: ast.Call) -> Any:
            nonlocal provider, tool_name
            if provider and tool_name:
                return
            func_node = node.func
            call_name = _call_name(func_node)
            if call_name not in {"call_tool", "_invoke_mcp_tool"}:
                self.generic_visit(node)
                return

            args = node.args or []
            if len(args) < 2:
                self.generic_visit(node)
                return
            first, second = args[0], args[1]
            provider_value = self._string_value(first)
            tool_value = self._string_value(second)
            if provider_value and tool_value:
                provider = provider_value
                tool_name = tool_value
                return
            self.generic_visit(node)

    Visitor().visit(tree)
    return provider, tool_name


def fingerprint_manifest(data: Any) -> str:
    """Return a stable sha256 fingerprint for manifest dictionaries."""
    if is_dataclass(data):
        payload = json.dumps(asdict(data), sort_keys=True)
    else:
        payload = json.dumps(data, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json_if_changed(path: Path, payload: Dict[str, Any]) -> bool:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    ensure_dir(path.parent)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == serialized:
            return False
    path.write_text(serialized, encoding="utf-8")
    return True


def default_toolbox_root() -> Path:
    configured = os.getenv("MCP_TOOLBOX_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (repo_root() / "toolbox").resolve()


def safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def write_text_if_changed(path: Path, content: str) -> bool:
    ensure_dir(path.parent)
    content_with_nl = content if content.endswith("\n") else content + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content_with_nl:
            return False
    path.write_text(content_with_nl, encoding="utf-8")
    return True


def _split_identifier(value: str) -> list[str]:
    parts = re.split(r"[^0-9A-Za-z]+", value)
    return [part for part in parts if part]


def to_camel_case(value: str) -> str:
    parts = _split_identifier(value)
    if not parts:
        return value
    first = parts[0].lower()
    rest = "".join(part.capitalize() for part in parts[1:])
    return first + rest


def to_pascal_case(value: str) -> str:
    parts = _split_identifier(value)
    if not parts:
        return value.title()
    return "".join(part.capitalize() for part in parts)


def to_snake_case(value: str) -> str:
    parts = _split_identifier(value)
    if not parts:
        return value
    return "_".join(part.lower() for part in parts)


def flatten_schema_fields(
    schema: Dict[str, Any],
    *,
    prefix: str = "",
    depth: int = 0,
    max_depth: Optional[int] = None,
    max_fields: int = 40,
    out: Optional[List[str]] = None,
) -> List[str]:
    """
    Flatten a JSON-schema-like dict into a list of 'path: type' strings.

    This utility extracts field paths from nested JSON schemas to provide
    a compact representation of data structures for LLM context.

    Args:
        schema: JSON schema dict to flatten
        prefix: Current path prefix (for recursion)
        depth: Current recursion depth
        max_depth: Maximum depth to traverse (None = unlimited)
        max_fields: Maximum number of fields to extract
        out: Output list to append to (for recursion)

    Returns:
        List of field paths like ["messages[].id", "messages[].subject", ...]

    Examples:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string"},
        ...         "items": {
        ...             "type": "array",
        ...             "items": {
        ...                 "type": "object",
        ...                 "properties": {
        ...                     "id": {"type": "number"}
        ...                 }
        ...             }
        ...         }
        ...     }
        ... }
        >>> flatten_schema_fields(schema)
        ['name: string', 'items[]: object', 'items[].id: number']
    """
    if out is None:
        out = []

    if max_fields is not None and len(out) >= max_fields:
        return out

    if max_depth is not None and depth > max_depth:
        return out

    if not isinstance(schema, dict):
        return out

    schema_type = schema.get("type")
    props = schema.get("properties", {})

    # If this is an envelope with a top-level "data" property, dive into it
    # without emitting the "data" prefix so callers see the inner fields directly.
    # If data has no type/properties, emit a placeholder so the caller can still
    # reference data safely.
    if depth == 0 and isinstance(props, dict) and "data" in props:
        data_schema = props.get("data")
        if isinstance(data_schema, dict):
            data_type = data_schema.get("type") or "object"
            data_props = data_schema.get("properties") or {}
            # If data has no children, emit the data path with its type
            if not data_props:
                out.append(f"{prefix + '.' if prefix else ''}data: {data_type}")
                return out
            return flatten_schema_fields(
                data_schema,
                prefix=prefix,
                depth=depth,
                max_depth=max_depth,
                max_fields=max_fields,
                out=out,
            )

    if schema_type and not props:
        if prefix:
            out.append(f"{prefix}: {schema_type}")
        return out

    for name, subschema in props.items():
        if max_fields is not None and len(out) >= max_fields:
            break

        if isinstance(subschema, dict) and subschema.get("type") == "array":
            item = subschema.get("items", {})
            child_prefix = f"{prefix}.{name}[]" if prefix else f"{name}[]"
            # If items schema is empty/unknown, still emit the array path
            if (
                not isinstance(item, dict)
                or not item
                or (not item.get("type") and not item.get("properties"))
            ):
                out.append(f"{child_prefix}: {subschema.get('type', 'array')}")
                continue
            flatten_schema_fields(
                item,
                prefix=child_prefix,
                depth=depth + 1,
                max_depth=max_depth,
                max_fields=max_fields,
                out=out,
            )
        else:
            child_prefix = f"{prefix}.{name}" if prefix else name
            flatten_schema_fields(
                subschema,
                prefix=child_prefix,
                depth=depth + 1,
                max_depth=max_depth,
                max_fields=max_fields,
                out=out,
            )

    return out
