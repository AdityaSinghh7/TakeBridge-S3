# MCP Agent Extension Guide: Providers & Tools

This document outlines the precise, end-to-end workflow for extending the MCP Agent capabilities. It covers configuration, action wrappers, and output schemas.

## Core Architecture

1. **Configuration Layer**: Maps providers to authentication config IDs and ensures environment variables (tokens/URLs) are injected into the runtime.
2. **Wrapper Layer (`mcp_agent/actions/wrappers/`)**: Python functions that wrap the low-level MCP client calls, handling parameter normalization and context injection.
3. **Output Schema Annotations**: Each wrapper attaches `__tb_output_schema__` (and optional `__tb_output_schema_pretty__`) to describe the tool's `data` payload.

---

## Phase 1: Configuration (OAuth & Environment)

*Skip this phase if adding a tool to an existing provider.*

If adding a **new provider**, you must register its Auth Config ID and add it to the environment synchronization loops to ensure tokens are available at runtime.

### 1. OAuth Config Mapping

**File:** `mcp_agent/registry/oauth.py`

Add the new provider to the `AUTH_CONFIG_IDS` dictionary. This tells the system which Composio Auth Config ID to use.

```python
# mcp_agent/registry/oauth.py

AUTH_CONFIG_IDS = {
    "gmail": os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID", ""),
    "slack": os.getenv("COMPOSIO_SLACK_AUTH_CONFIG_ID", ""),
    "github": os.getenv("COMPOSIO_GITHUB_AUTH_CONFIG_ID", ""),  # <--- Add new provider
}
```

### 2. Environment Synchronization

You must ensure the new provider's environment variables (tokens, connection URLs) are synced before execution. Update the loop in the following **three** files:

- **`mcp_agent/agent/run_loop.py`** (inside `execute_mcp_task`)
- **`mcp_agent/execution/runner.py`** (inside `run_python_plan`)
- **`mcp_agent/sandbox/glue.py`** (inside `register_default_tool_caller`)

**Change:**

```python
# Update the tuple to include your new provider string
for provider in ("gmail", "slack", "github"):
    ensure_env_for_provider(..., provider)
```

---

## Phase 2: Implementation (Action Wrappers)

All tool logic resides in `mcp_agent/actions/wrappers/`.

### 1. Creating the Wrapper

A wrapper function must accept `context: AgentContext` as the first argument, followed by the tool's specific arguments. It must return a `ToolInvocationResult`.

**Standard Wrapper Template:**

```python
# mcp_agent/actions/wrappers/<provider_name>.py

from typing import TYPE_CHECKING, Any
from mcp_agent.types import ToolInvocationResult
from ._common import _clean_payload, ensure_authorized, _invoke_mcp_tool

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

def <provider>_<tool_name>(
    context: AgentContext,
    arg1: str,
    arg2: int = 10,
    # ... other args
) -> ToolInvocationResult:
    """
    Docstring describing the tool.
    """
    tool_name = "<MCP_TOOL_NAME>"  # The actual tool name on the MCP server

    # 1. Check Authorization
    ensure_authorized(context, "<provider_name>")

    # 2. Construct Payload (clean out None values)
    payload = _clean_payload({
        "param_key": arg1,
        "other_key": arg2
    })

    # 3. Invoke
    return _invoke_mcp_tool(context, "<provider_name>", tool_name, payload)
```

### 2. Registering the Provider

Providers are discovered automatically from modules under `mcp_agent/actions/wrappers/`.

To add a new provider, create a new `<provider>.py` module with at least one public wrapper.

---

## Phase 3: Output Schemas (Wrapper Annotations)

To allow the agent to understand the structure of the tool's output, attach a schema to the wrapper using `__tb_output_schema__` (and optionally `__tb_output_schema_pretty__`).

Use the decorator from `mcp_agent/tool_schemas.py` or set the attribute directly:

```python
from mcp_agent.tool_schemas import tool_output_schema


@tool_output_schema(
    schema={
        "properties": {
            "data": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                },
            }
        }
    },
    pretty="""
Canonical wrapper: { successful: bool, data: dict, error: str | null }

data: {
  id: string,
  name: string,
}
""".strip(),
)
def <provider>_<tool_name>(...):
    ...
```

---

## Implementation Scenarios

### Case 1: Adding a new Tool to an existing Provider

**Scenario:** Adding `gmail_get_profile` to the existing `gmail` provider.

1. **Wrapper:** Open `mcp_agent/actions/wrappers/gmail.py` and add the function.
2. **Schema:** Attach `__tb_output_schema__` (or `@tool_output_schema`) to the wrapper.

### Case 2: Adding a New Provider (No Tools yet)

**Scenario:** Adding `github` provider scaffold.

1. **Config:**
   - Update `AUTH_CONFIG_IDS` in `mcp_agent/registry/oauth.py`.
   - Update env sync loops in `agent/run_loop.py`, `execution/runner.py`, and `sandbox/glue.py`.
2. **Wrapper:** Create `mcp_agent/actions/wrappers/github.py` (empty scaffold).
3. **Schema:** Attach `__tb_output_schema__` when you add tools.

### Case 3: Adding a New Provider + New Tools

**Scenario:** Adding `github` provider with `github_create_issue`.

1. **Config:**
   - Update `AUTH_CONFIG_IDS` in `mcp_agent/registry/oauth.py`.
   - Update env sync loops in `agent/run_loop.py`, `execution/runner.py`, and `sandbox/glue.py`.
2. **Wrapper:** Create `mcp_agent/actions/wrappers/github.py` with `github_create_issue`.
3. **Schema:** Attach `__tb_output_schema__` (or `@tool_output_schema`) to the wrapper.

---

## Summary Checklist

| Step | Action | File(s) Affected |
| :--- | :--- | :--- |
| 1 | **Config** | `registry/oauth.py`<br>`agent/run_loop.py`<br>`execution/runner.py`<br>`sandbox/glue.py` |
| 2 | **Wrapper** | `actions/wrappers/<provider>.py` |
| 3 | **Schema** | `actions/wrappers/<provider>.py` (attach `__tb_output_schema__`) |
