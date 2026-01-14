# Adding MCP Providers and Tools (Current Workflow)

This document is the up-to-date, code-aligned guide for extending the MCP agent.
It focuses on the exact data required to add:
- a new tool for an existing provider,
- a new provider (with or without tools),
- a new provider and tools together.

Primary code paths:
- Wrappers: `mcp_agent/actions/wrappers/`
- Provider discovery: `mcp_agent/actions/provider_loader.py`
- Tool metadata: `mcp_agent/knowledge/introspection.py`
- Docstring parsing: `mcp_agent/knowledge/utils.py`
- Search output: `mcp_agent/knowledge/search.py`
- Output schema decorator: `mcp_agent/tool_schemas.py`

---

## How input_params and output_fields are generated

### input_params (tool inputs)
`ToolSpec` is built from wrapper signatures + docstrings:
- `mcp_agent/knowledge/introspection.py` calls `parse_action_docstring(...)` in
  `mcp_agent/knowledge/utils.py`.
- It reads `Description:` and `Args:` blocks in the docstring.
- Parameter names must match the function signature.
- The first parameter `context: AgentContext` is ignored for tool inputs.
- Required vs optional is determined by whether a default exists.

`ToolSpec.to_compact_descriptor()` produces `input_params`, a dict like:
```
{
  "query": "str (required) - Gmail search query",
  "max_results": "int (optional, default=20) - Max results to return"
}
```
This is what the planner and sandbox validator use.

Docstring parsing rules (from `parse_action_docstring`):
- `Description:` lines form the short description.
- `Args:` lines must be `name: text` and the name must exist in the signature.
- Continued lines under `Args:` are appended to the prior param description.

### output_fields (tool outputs)
Tool outputs come from `__tb_output_schema__` attached to each wrapper:
- The schema can be the full envelope or just the `data` payload.
- If the schema includes top-level `properties.data`, it is automatically
  unwrapped for summarization.
- `summarize_schema_for_llm(...)` creates `output_fields`:
  - leaf paths like `messages[].subject: string`
  - fold markers for large objects/arrays, e.g.:
    `orders[]: object (contains 15 sub-fields; inspect_tool_output(..., field_path="orders[]"))`

If the schema is large, `has_hidden_fields` will be true and you must use
`inspect_tool_output` (see `mcp_agent/actions/wrappers/toolbox.py`) to drill
down.

---

## Data required for any new tool

You must provide the following data for each new wrapper tool:

1. **Provider ID**
   - String used in the wrapper module name and `_invoke_mcp_tool` call.
   - Example: `"gmail"` for `mcp_agent/actions/wrappers/gmail.py`.

2. **Wrapper function name**
   - Public function name becomes the tool name and `tool_id`.
   - `tool_id` is `{provider}.{function_name}` (e.g., `gmail.gmail_search`).

3. **MCP tool name (Composio)**
   - The actual MCP tool constant passed to `_invoke_mcp_tool`.
   - Example: `"GMAIL_SEND_EMAIL"`.

4. **Signature + defaults**
   - Types + defaults define required/optional inputs.
   - Optional params must have defaults.

5. **Docstring with Description/Args**
   - `Description:` and `Args:` blocks drive input_params descriptions.
   - Param names must match the signature.

6. **Output schema**
   - Attach `__tb_output_schema__` (full envelope or data schema).
   - This drives `output_fields` and `inspect_tool_output`.

Optional:
- `__tb_output_schema_pretty__` (human-readable lines) using `@tool_output_schema`.
- Put large schemas into helper modules (see `mcp_agent/actions/slack_output_helper.py`).

---

## Add a new tool to an existing provider

### 1) Implement the wrapper
**File:** `mcp_agent/actions/wrappers/<provider>.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING
from mcp_agent.types import ToolInvocationResult
from ._common import _clean_payload, ensure_authorized, _invoke_mcp_tool

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def gmail_archive_thread(
    context: "AgentContext",
    thread_id: str,
) -> ToolInvocationResult:
    """
    Description:
        Archive a Gmail thread by ID.
    Args:
        thread_id: Gmail thread ID to archive.
    """
    provider = "gmail"
    tool_name = "GMAIL_ARCHIVE_THREAD"
    ensure_authorized(context, provider)
    payload = _clean_payload({"thread_id": thread_id})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


gmail_archive_thread.__tb_output_schema__ = {
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "threadId": {"type": "string"},
                "archived": {"type": "boolean"},
            },
        },
        "successful": {"type": "boolean"},
        "error": {"type": "string"},
    }
}
```

### 2) Verify discovery
```python
from mcp_agent.knowledge.search import search_tools

tools = search_tools(query="gmail archive", user_id="dev-local")
assert any(t["tool_id"] == "gmail.gmail_archive_thread" for t in tools)
```

If `output_fields` is empty, your `__tb_output_schema__` is missing or invalid.

---

## Add a new provider (no tools yet)

Providers are auto-discovered by scanning `mcp_agent/actions/wrappers/`.
Only modules with at least one public function are included.

Required data:
1. **Provider ID** (module name)
2. **Composio Auth Config ID**

Steps:
1) Add the Composio auth config mapping:
   - File: `mcp_agent/registry/oauth.py`
   - Update `AUTH_CONFIG_IDS` with:
     `"yourprovider": os.getenv("COMPOSIO_YOURPROVIDER_AUTH_CONFIG_ID", "")`

2) Create wrapper module:
   - File: `mcp_agent/actions/wrappers/yourprovider.py`
   - Add at least one public wrapper (otherwise the provider is not discovered).

3) Ensure the provider is authorized in DB:
   - `search_tools(...)` only returns providers that are authorized.

Optional:
- Add the provider to `PROVIDER_FAMILIES` in `mcp_agent/knowledge/search.py`
  for better matching in tool search.

---

## Add a new provider + new tools

Combine the two flows:
1) Add provider auth config ID in `mcp_agent/registry/oauth.py`.
2) Create `mcp_agent/actions/wrappers/<provider>.py`.
3) Add tools with correct signatures, docstrings, and output schemas.
4) Verify with `search_tools(...)`.

---

## Common pitfalls

- **Docstring param names do not match signature**: descriptions are dropped.
- **Missing `__tb_output_schema__`**: `output_fields` empty, inspect fails.
- **Wrapper function imported from elsewhere**: discovery ignores it (only
  functions defined in the module are included).
- **Module name starts with "_"**: provider is skipped by discovery.
- **Provider not authorized**: it will not appear in search results.

---

## Quick reference: file locations

- Wrappers: `mcp_agent/actions/wrappers/<provider>.py`
- Provider discovery: `mcp_agent/actions/provider_loader.py`
- Tool metadata + docstring parsing: `mcp_agent/knowledge/introspection.py`
- Docstring parser: `mcp_agent/knowledge/utils.py`
- Output schema decorator: `mcp_agent/tool_schemas.py`
- Search entrypoint: `mcp_agent/knowledge/search.py`
