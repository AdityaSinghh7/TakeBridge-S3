# MCP Agent

Provider-agnostic MCP tooling that powers both the standalone planner and the computer-use agent.

## Architecture Overview

The MCP Agent follows a clean layered architecture:

- **Core Layer** (`core/`): `AgentContext` for multi-tenant context management
- **Registry Layer** (`registry/`): Provider registry and OAuth token management
- **Actions Layer** (`actions/`): Tool wrappers and dispatcher
- **Execution Layer** (`execution/`): Sandbox execution and response normalization
- **Knowledge Layer** (`knowledge/`): Tool indexing, search, and discovery views
- **Agent Layer** (`agent/`): Planning and orchestration logic

## Adding A New Provider

Follow these steps to introduce a new provider without touching planner logic:

1. **Create wrappers in `mcp_agent/actions/wrappers/`:**
   - Create a new file for your provider (e.g., `github.py`)
   - Each wrapper function should:
     - Accept `AgentContext` as the first parameter
     - Accept tool-specific parameters as keyword arguments
     - Normalize parameters inside the wrapper (strings vs lists, structured payloads)
     - Call `_invoke_mcp_tool(context, provider, TOOL_NAME, payload)` to execute
     - Return a standardized `ToolInvocationResult`

2. **Register the wrapper:**
   - Import the new module in `mcp_agent/actions/__init__.py`
   - Add to `get_provider_action_map()` so the dispatcher can find your tools
   - Ensure provider OAuth configuration exists in `RegistryManager`

3. **Refresh toolbox artifacts:**
   - Run the toolbox builder to update `toolbox/manifest.json` and generated sandbox stubs
   - This makes the new provider available in the sandbox environment

4. **Write/extend tests:**
   - Add unit tests covering normalization rules and error handling
   - Test the wrapper independently using mock `AgentContext`

With these steps complete, planners can discover and use the new provider via `search_tools(...)` and `dispatch_tool(...)`.

## Example Wrapper

```python
from mcp_agent.core.context import AgentContext
from mcp_agent.types import ToolInvocationResult
from mcp_agent.registry.manager import RegistryManager

def github_create_issue(
    context: AgentContext,
    repo: str,
    title: str,
    body: str = "",
) -> ToolInvocationResult:
    """Create a GitHub issue."""
    # Check authorization
    registry = RegistryManager(context)
    if not registry.is_provider_available("github"):
        return {
            "successful": False,
            "data": {},
            "error": "GitHub provider not authorized"
        }

    # Call MCP tool
    payload = {"repo": repo, "title": title, "body": body}
    return _invoke_mcp_tool(context, "github", "GITHUB_CREATE_ISSUE", payload)
```
