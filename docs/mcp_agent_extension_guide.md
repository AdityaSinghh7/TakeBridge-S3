# MCP Agent Extension Guide: Providers & Tools

This document outlines the precise, end-to-end workflow for extending the MCP Agent capabilities. It covers Configuration, Action Wrappers, Output Samples, and Schema Generation.

## Core Architecture

1. **Configuration Layer**: Maps providers to authentication config IDs and ensures environment variables (tokens/URLs) are injected into the runtime.
2. **Wrapper Layer (`mcp_agent/actions/wrappers/`)**: Python functions that wrap the low-level MCP client calls, handling parameter normalization and context injection.
3. **Sample Definition (`tool_output_samples.yaml`)**: Real-world examples of inputs used to probe the tools.
4. **Schema Generation (`scripts/generate_tool_output_schemas.py`)**: A script that executes the wrappers using the samples to infer the exact JSON structure of the output.

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
- **`mcp_agent/sandbox/runner.py`** (inside `run_python_plan`)
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
from mcp_agent.core.exceptions import UnauthorizedError
from mcp_agent.registry import is_provider_available
from mcp_agent.types import ToolInvocationResult
from mcp_agent.user_identity import normalize_user_id
# Import helper functions from sibling modules if necessary
from ._helpers import _invoke_mcp_tool

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
    tool_name = "<MCP_TOOL_NAME>" # The actual tool name on the MCP server
    user_id = normalize_user_id(context.user_id)

    # 1. Check Authorization
    if not is_provider_available(context, "<provider_name>"):
        raise UnauthorizedError("<provider_name>", user_id)

    # 2. Construct Payload
    payload = {
        "param_key": arg1,
        "other_key": arg2
    }

    # 3. Invoke
    return _invoke_mcp_tool(context, "<provider_name>", tool_name, payload)
```

### 2. Registering the Provider

If this is a **new provider**, register it in the actions initialization file.

**File:** `mcp_agent/actions/__init__.py`

```python
# Add string identifier to SUPPORTED_PROVIDERS
SUPPORTED_PROVIDERS: tuple[str, ...] = ("gmail", "slack", "<new_provider>")
```

---

## Phase 3: Definition (Output Samples)

To allow the agent to understand the structure of the tool's output, we must probe the tool with real requests.

**File:** `tool_output_samples.yaml`

Add an entry using the format `<provider>.<function_name>`.

```yaml
<provider>.<function_name>:
  mode: read  # Use 'mutate' if the tool modifies data (e.g., sending emails)
  success_examples:
    - args:
        arg1: "valid_value"
        arg2: 10
  error_examples:
    - args:
        arg1: "invalid_value_to_trigger_error"
        arg2: 0
```

**Guidelines:**

- **Mode:** `read` for safe operations (search, get); `mutate` for state-changing operations (post, send).
- **Args:** Must match the python signature arguments of your wrapper function (excluding `context`).

---

## Phase 4: Generation (Schema Inference)

Run the generation script to execute samples against live MCP tools and infer schemas.

**Script:** `scripts/generate_tool_output_schemas.py`

### Selective Generation (Crucial)

Always use the `--providers` flag to prevent re-probing the entire toolset.

**Command:**

```bash
python scripts/generate_tool_output_schemas.py \
  --providers <provider_name> \
  --user-id <dev_user_id>
```

- **`--providers`**: Comma-separated list. Replaces existing schemas for these providers; keeps others intact.
- **`--allow-mutating`**: Required if your tool is `mode: mutate`.

---

## Implementation Scenarios

### Case 1: Adding a new Tool to an existing Provider

**Scenario:** Adding `gmail_get_profile` to the existing `gmail` provider.

1. **Wrapper:** Open `mcp_agent/actions/wrappers/gmail.py` and add the function.
2. **Samples:** Open `tool_output_samples.yaml` and add `gmail.gmail_get_profile` examples.
3. **Generation:**

```bash
python scripts/generate_tool_output_schemas.py --providers gmail --user-id dev-local
```

### Case 2: Adding a New Provider (No Tools yet)

**Scenario:** Adding `github` provider scaffold.

1. **Config:**
   - Update `AUTH_CONFIG_IDS` in `mcp_agent/registry/oauth.py`.
   - Update env sync loops in `agent/run_loop.py`, `sandbox/runner.py`, and `sandbox/glue.py`.
2. **Wrapper:** Create `mcp_agent/actions/wrappers/github.py` (empty scaffold).
3. **Registration:** Update `SUPPORTED_PROVIDERS` in `mcp_agent/actions/__init__.py`.
4. **Generation:** Skip.

### Case 3: Adding a New Provider + New Tools

**Scenario:** Adding `github` provider with `github_create_issue`.

1. **Config:**
   - Update `AUTH_CONFIG_IDS` in `mcp_agent/registry/oauth.py`.
   - Update env sync loops in `agent/run_loop.py`, `sandbox/runner.py`, and `sandbox/glue.py`.
2. **Wrapper:** Create `mcp_agent/actions/wrappers/github.py` with `github_create_issue`.
3. **Registration:** Update `SUPPORTED_PROVIDERS` in `mcp_agent/actions/__init__.py`.
4. **Samples:** Add `github.github_create_issue` to `tool_output_samples.yaml`.
5. **Generation:**

```bash
python scripts/generate_tool_output_schemas.py \
  --providers github \
  --user-id dev-local \
  --allow-mutating
```

---

## Summary Checklist

| Step | Action | File(s) Affected |
| :--- | :--- | :--- |
| 1 | **Config** | `registry/oauth.py`<br>`agent/run_loop.py`<br>`sandbox/runner.py`<br>`sandbox/glue.py` |
| 2 | **Wrapper** | `actions/wrappers/<provider>.py` |
| 3 | **Register** | `actions/__init__.py` |
| 4 | **Sample** | `tool_output_samples.yaml` |
| 5 | **Generate** | Run `scripts/generate_tool_output_schemas.py` |
