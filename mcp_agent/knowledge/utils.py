from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import re
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Tool schema summarization (LLM-facing)
# ---------------------------------------------------------------------------

# Standardized Tier-1 regex used by the schema summarizer.
TIER_1_REGEX = r"(?:^|\.|\[\]\.)(id|.*_id|name|title|status|type|url|email|price|amount|created|updated|timestamp)$"

# Default summary budget for CompactToolDescriptor.output_fields
MAX_SUMMARY_FIELDS = 30


def repo_root() -> Path:
    return _REPO_ROOT


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_action_docstring(
    doc: str | None, param_names: set[str] | None = None
) -> tuple[str, Dict[str, str]]:
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
                candidate = name.strip()
                if param_names and candidate not in param_names:
                    # Treat unknown "name:" lines as continuation text.
                    if current_param:
                        param_docs[current_param] = f"{param_docs.get(current_param, '')} {line}".strip()
                    else:
                        description_lines.append(line)
                    continue
                current_param = candidate
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


def summarize_schema_for_llm(
    schema: Dict[str, Any],
    *,
    max_depth: int = 3,
    max_fields: int = MAX_SUMMARY_FIELDS,
) -> tuple[List[str], bool]:
    """
    Produce a compact, planner-friendly summary of a tool's output schema.

    Contract:
    - Prefer "Tier 1" leaf fields (IDs, names, statuses, etc.).
    - Always include top-level primitives.
    - For large nested containers, emit fold markers that instruct the planner
      to call `toolbox.inspect_tool_output(tool_id, field_path)` for drill-down.

    Returns:
        (output_fields, has_hidden_fields)
    """
    data_schema = _unwrap_data_envelope(schema)
    if not isinstance(data_schema, dict) or not data_schema:
        return [], False

    # Candidate leaves within the normal summary max_depth (bounded)
    candidate_leaves, candidate_truncated = _collect_leaf_fields(
        data_schema,
        max_depth=max_depth,
        max_nodes=8_000,
        max_results=max(500, max_fields * 30),
        return_truncation=True,
    )

    tier2_lines = _root_structural_lines(data_schema)

    # Fast-path: small schemas (keep previous behavior: no fold markers)
    if not candidate_truncated and len(candidate_leaves) <= max_fields:
        if candidate_leaves:
            # Preserve ordering from traversal.
            return candidate_leaves, False
        if tier2_lines:
            # Fall back to root structural lines when no leaves are visible.
            return tier2_lines, True
        if _is_unknown_object_schema(data_schema):
            return [
                'data: object (unknown keys; inspect_tool_output(..., field_path=""))'
            ], True
        return [], False

    # Tier-1: greedy scan (bounded for safety) only when we are summarizing.
    tier1_pattern = re.compile(TIER_1_REGEX)
    tier1_fields = _collect_leaf_fields(
        data_schema,
        match_path=lambda p: bool(tier1_pattern.search(p)),
        max_depth=20,
        max_nodes=8_000,
        max_results=200,
    )

    # Otherwise, build the "smart summary" view.
    selected: List[str] = []
    selected_set: set[str] = set()

    def _add(line: str) -> None:
        if not line or line in selected_set:
            return
        if len(selected) >= max_fields:
            return
        selected.append(line)
        selected_set.add(line)

    # 1) Tier-2 root primitives + fold markers for root containers (always visible)
    for line in tier2_lines:
        _add(line)

    # 2) Tier-1 leaf fields
    for line in tier1_fields:
        _add(line)

    # 3) Fill remaining budget with BFS leaf fields
    for line in candidate_leaves:
        _add(line)

    has_hidden_fields = True
    return selected, has_hidden_fields


def _unwrap_data_envelope(schema: Dict[str, Any]) -> Dict[str, Any]:
    """If schema is an envelope with top-level `data`, return that subtree."""
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    if isinstance(props, dict):
        data_schema = props.get("data")
        if isinstance(data_schema, dict):
            return data_schema
    return schema


def _schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    value = schema.get("type")
    if isinstance(value, str) and value:
        return value
    # Infer from shape
    if isinstance(schema.get("properties"), dict):
        return "object"
    if "items" in schema:
        return "array"
    if "oneOf" in schema or "anyOf" in schema:
        return "union"
    if "enum" in schema:
        return "enum"
    return "unknown"


def _has_properties(schema: Dict[str, Any]) -> bool:
    props = schema.get("properties")
    return isinstance(props, dict) and bool(props)


def _is_unknown_object_schema(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    if schema.get("type") == "object" and not _has_properties(schema):
        if schema.get("additionalProperties") is True:
            return True
    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if isinstance(options, list):
            for option in options:
                if _is_unknown_object_schema(option):
                    return True
    return False



def _array_item_schema(schema: Dict[str, Any]) -> Dict[str, Any] | None:
    items = schema.get("items")
    return items if isinstance(items, dict) else None


def _root_structural_lines(schema: Dict[str, Any]) -> List[str]:
    """
    Emit Tier-2 lines for immediate children of the root `data` object:
    - primitives as `key: type`
    - containers as fold markers with child counts and inspect hints
    """
    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return []

    lines: List[str] = []
    for name, subschema in props.items():
        if not isinstance(subschema, dict):
            continue
        child_type = _schema_type(subschema)

        # Primitive leaf at root
        if child_type in {"string", "number", "integer", "boolean", "null"} or child_type == "enum":
            lines.append(f"{name}: {child_type}")
            continue

        # Array handling
        if child_type == "array":
            item_schema = _array_item_schema(subschema) or {}
            item_type = _schema_type(item_schema)
            if item_type in {"string", "number", "integer", "boolean", "null"} or item_type == "enum":
                lines.append(f"{name}[]: {item_type}")
                continue
            child_count, unknown = _child_count(item_schema)
            if unknown:
                lines.append(
                    f'{name}[]: object (unknown keys; inspect_tool_output(..., field_path="{name}[]"))'
                )
            else:
                lines.append(
                    f'{name}[]: object (contains {child_count} sub-fields; inspect_tool_output(..., field_path="{name}[]"))'
                )
            continue

        # Object handling
        if child_type == "object" or child_type == "union":
            child_count, unknown = _child_count(subschema)
            if unknown:
                lines.append(
                    f'{name}: object (unknown keys; inspect_tool_output(..., field_path="{name}"))'
                )
            else:
                lines.append(
                    f'{name}: object (contains {child_count} sub-fields; inspect_tool_output(..., field_path="{name}"))'
                )
            continue

        # Fallback
        lines.append(f"{name}: {child_type}")

    return lines


def _child_count(schema: Dict[str, Any]) -> tuple[int, bool]:
    """Return (immediate_property_count, unknown)."""
    props = schema.get("properties")
    if isinstance(props, dict):
        return len(props), False
    # additionalProperties without explicit properties => unknown shape
    if schema.get("additionalProperties") is True:
        return 0, True
    return 0, True


def _collect_leaf_fields(
    schema: Dict[str, Any],
    *,
    match_path: Optional[Callable[[str], bool]] = None,
    max_depth: int = 3,
    max_nodes: int = 5_000,
    max_results: int = 2_000,
    return_truncation: bool = False,
) -> Any:
    """
    BFS over a JSON-schema-like dict, collecting leaf `path: type` strings.

    - Respects `max_depth` (object/array edges).
    - Stops after `max_nodes` visited nodes.
    - Stops after `max_results` collected leaves.
    - If `match_path` is provided, collects only leaves whose path matches.
    """
    leaves: List[str] = []
    nodes_visited = 0

    # Queue elements: (schema_node, path_prefix, depth)
    queue: deque[tuple[Dict[str, Any], str, int]] = deque()
    queue.append((schema, "", 0))

    while queue:
        node, prefix, depth = queue.popleft()
        nodes_visited += 1
        if nodes_visited > max_nodes:
            break
        if len(leaves) >= max_results:
            break

        node_type = _schema_type(node)

        # Depth cap applies to descending; still allow emitting leaves at the boundary.
        if depth > max_depth:
            continue

        props = node.get("properties") if isinstance(node, dict) else None
        if node_type == "object" and isinstance(props, dict) and props:
            if depth == max_depth:
                continue
            for name, child in props.items():
                if not isinstance(child, dict):
                    continue
                child_prefix = f"{prefix}.{name}" if prefix else name
                queue.append((child, child_prefix, depth + 1))
            continue

        if node_type == "array":
            if depth == max_depth:
                continue
            item_schema = _array_item_schema(node)
            child_prefix = f"{prefix}[]" if prefix else "[]"
            if isinstance(item_schema, dict) and item_schema:
                queue.append((item_schema, child_prefix, depth + 1))
            else:
                # Unknown items: emit array placeholder if we have a named prefix.
                if prefix:
                    path_only = prefix + "[]"
                    if match_path is None or match_path(path_only):
                        leaves.append(f"{path_only}: array")
            continue

        # Leaf / unknown
        if prefix:
            path_only = prefix
            if match_path is None or match_path(path_only):
                leaf_type = node_type
                leaves.append(f"{path_only}: {leaf_type}")

    truncated = bool(queue) or nodes_visited > max_nodes or len(leaves) >= max_results
    if return_truncation:
        return leaves, truncated
    return leaves
