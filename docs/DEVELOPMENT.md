# Development Guide

This guide covers development workflows for the MCP Agent, including adding new tools/providers, testing, and customizing tool parameters.

## Development Setup

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration
```

### Database Setup

```bash
# Run migrations (if using Alembic)
alembic upgrade head

# Or initialize database manually
python -c "from server.db import init_db; init_db()"
```

### OAuth Configuration

Configure Composio OAuth in `.env`:

```bash
COMPOSIO_API_KEY=your_api_key
OAUTH_REDIRECT_BASE=http://localhost:8000
```

---

## Testing with Scripts

The repository includes several scripts for testing the MCP Agent:

### Run Development Task

```bash
# Execute a task with the MCP Agent
./scripts/run_dev_mcp_task.py --user-id dev-local
```

**Options:**
- `--task`: Custom task string
- `--user-id`: User identifier (default: dev-local)
- `--model`: LLM model (default: o4-mini)
- `--pretty`: Pretty-print JSON output

**Example:**
```bash
./scripts/run_dev_mcp_task.py \
  --task "Search my Gmail for unread emails and post count to #general" \
  --user-id dev-local \
  --model o4-mini \
  --pretty
```

### Generate Tool Output Schemas

```bash
# Generate schemas from tool output samples
./scripts/generate_tool_output_schemas.py \
  --user-id dev-local \
  --providers gmail,slack
```

**Options:**
- `--user-id`: User for MCP registry
- `--providers`: Comma-separated provider list
- `--skip-unconfigured`: Skip unconfigured providers
- `--allow-mutating`: Allow sampling mutating tools (use carefully!)

### Build Tool Output Schemas (Legacy)

```bash
# Build schemas from samples file
./scripts/build_tool_output_schemas.py
```

Reads `tool_output_samples.json` and generates `tool_output_schemas.json`.

### Probe Tools

```bash
# Test MCP tool connectivity
./scripts/probe_tools.py
```

Tests Gmail and Slack MCP connections with sample calls.

---

## Adding New Tools

### Adding a Tool to an Existing Provider

Example: Add `gmail_archive_thread` to Gmail.

#### 1. Implement the Wrapper

**File:** `mcp_agent/actions/wrappers/gmail.py`

```python
from mcp_agent.actions.core import mcp_action, ToolInvocationResult

@mcp_action
def gmail_archive_thread(self, thread_id: str) -> ToolInvocationResult:
    """
    Archive a Gmail thread by ID.

    Args:
        thread_id: Gmail thread ID to archive
    """
    tool_name = "GMAIL_ARCHIVE_THREAD"
    payload = {"thread_id": thread_id}
    return self._invoke_mcp_tool("gmail", tool_name, payload)
```

**Key Requirements:**
- Use `@mcp_action` decorator
- Include docstring with `Description` and `Args`
- Accurate type annotations in signature
- Return `ToolInvocationResult` (normalized response)

#### 2. Document Output Schema

Add output schema decorator:

```python
from mcp_agent.knowledge.schema_store import tool_output_schema

@tool_output_schema(
    schema={
        "threadId": "string",
        "archived": "boolean",
    },
    pretty="""
threadId: string - The archived thread ID
archived: boolean - Whether the thread was successfully archived
    """.strip()
)
@mcp_action
def gmail_archive_thread(self, thread_id: str) -> ToolInvocationResult:
    ...
```

#### 3. Update Tool Output Schemas

Add to `tool_output_samples.yaml`:

```yaml
gmail.gmail_archive_thread:
  mode: mutate  # read or mutate
  success_examples:
    - args:
        thread_id: "thread_abc123"
```

Regenerate schemas:

```bash
./scripts/generate_tool_output_schemas.py \
  --user-id dev-local \
  --providers gmail \
  --allow-mutating
```

#### 4. Verify Discovery

```python
from mcp_agent.knowledge.search import search_tools

tools = search_tools(
    query="gmail archive",
    user_id="dev-local",
    detail_level="full"
)

# Should include gmail.gmail_archive_thread
print([t["tool_id"] for t in tools])
```

### Adding a New Provider

Example: Add Notion support.

#### 1. Create Wrapper Module

**File:** `mcp_agent/actions/wrappers/notion.py`

```python
from typing import Any, Dict, Optional
from mcp_agent.actions.core import ActionProvider, mcp_action, ToolInvocationResult

class NotionActions(ActionProvider):
    """Notion MCP action wrappers."""

    @mcp_action
    def notion_create_page(
        self,
        parent_id: str,
        title: str,
        content: str = "",
    ) -> ToolInvocationResult:
        """
        Create a new Notion page.

        Args:
            parent_id: Parent page or database ID
            title: Page title
            content: Page content in Markdown
        """
        tool_name = "NOTION_CREATE_PAGE"
        payload = {
            "parent_id": parent_id,
            "title": title,
            "content": content,
        }
        return self._invoke_mcp_tool("notion", tool_name, payload)

    @mcp_action
    def notion_search(
        self,
        query: str,
        limit: int = 10,
    ) -> ToolInvocationResult:
        """
        Search Notion workspace.

        Args:
            query: Search query string
            limit: Maximum number of results
        """
        tool_name = "NOTION_SEARCH"
        payload = {"query": query, "limit": limit}
        return self._invoke_mcp_tool("notion", tool_name, payload)
```

#### 2. Register Provider

**File:** `mcp_agent/actions/registry.py`

```python
from .wrappers.notion import NotionActions

PROVIDER_ACTIONS = {
    "gmail": GmailActions,
    "slack": SlackActions,
    "notion": NotionActions,  # Add here
}
```

#### 3. Configure MCP Client

Ensure OAuth/MCP integration is set up in:
- `mcp_agent/registry/oauth.py` (OAuth flow)
- `mcp_agent/registry/crud.py` (Client creation)

#### 4. Add Output Schemas

Create `tool_output_samples.yaml` entries:

```yaml
notion.notion_create_page:
  mode: mutate
  success_examples:
    - args:
        parent_id: "parent_123"
        title: "Test Page"
        content: "# Hello World"

notion.notion_search:
  mode: read
  success_examples:
    - args:
        query: "project notes"
        limit: 5
```

#### 5. Generate Schemas & Test

```bash
# Generate schemas
./scripts/generate_tool_output_schemas.py \
  --user-id dev-local \
  --providers notion \
  --allow-mutating

# Test with agent
./scripts/run_dev_mcp_task.py \
  --task "Search my Notion for 'project notes'" \
  --user-id dev-local
```

---

## Customizing Tool Parameters

### Change Parameter Names

Edit the function signature to use user-friendly names, then map to API names internally:

```python
@mcp_action
def gmail_send_email(
    self,
    recipient: str,  # User-friendly name
    subject: str,
    message: str,    # Changed from "body"
):
    # Map to Composio's expected names
    payload = {
        "to": recipient,
        "subject": subject,
        "body": message,
    }
    return self._invoke_mcp_tool("gmail", "GMAIL_SEND_EMAIL", payload)
```

### Make Parameters Optional/Required

Add or remove default values:

```python
# Make max_results required (no default)
def gmail_search(
    self,
    query: str,
    max_results: int,  # Required (no default)
):
    pass

# Make subject optional (add default)
def gmail_send_email(
    self,
    to: str,
    subject: str = "No Subject",  # Optional with default
    body: str = "",               # Optional with default
):
    pass
```

### Change Parameter Types

Update type annotations:

```python
def gmail_search(
    self,
    query: str,
    max_results: int | str = 20,  # Accept int or str
    include_payload: bool | None = None,  # Optional boolean
):
    pass
```

### Add Parameter Descriptions

Add detailed Args section in docstring:

```python
@mcp_action
def gmail_send_email(
    self,
    to: str,
    subject: str,
    body: str,
):
    """
    Send an email via Gmail API.

    Args:
        to: Comma-separated email addresses of recipients
        subject: Email subject line (supports UTF-8)
        body: Email body content (plain text or HTML)
    """
    pass
```

---

## Canonical Response Format

All MCP tool wrappers return a normalized `ActionResponse`:

```python
{
    "successful": bool,       # Canonical success flag
    "data": dict,            # Tool-specific output (always dict)
    "error": str | None,     # Error message or None
    "raw": Any | None,       # Original provider response (debug only)
}
```

**Sandbox Code Access:**

```python
# In sandbox code, tools return wrapped responses:
resp = await gmail.gmail_search(query="is:unread", max_results=5)

# Check success first
if not resp["successful"]:
    return {"error": resp["error"]}

# Access tool data
messages = resp["data"].get("messages", [])
for msg in messages:
    print(msg["messageId"], msg["subject"])
```

**Sandbox wrapper contract:**
- Sandbox snippets are injected into a pre-defined `async def main()` in `mcp_agent/execution/runner.py`; write only the body.
- Top-level `await` is valid in the snippet; place imports at the top of the snippet (inside main).
- Do not define `async def main`, `def main`, `if __name__ == "__main__"`, or call `asyncio.run(...)`.
- Violations return `sandbox_invalid_body`. Returning an empty result after tool calls returns `sandbox_empty_result`.

---

## Tool Search API

The planner discovers tools via the search API:

```python
from mcp_agent.knowledge.search import search_tools

# Search by query
tools = search_tools(
    query="gmail send",
    user_id="dev-local",
    detail_level="full",  # "summary" or "full"
    limit=10
)

# Each tool includes:
# - tool_id, provider, server, module, function
# - call_signature (copy-pasteable for sandbox)
# - description
# - input_params (structured parameter info)
# - output_fields (flat list of response fields)
# - score (relevance)
```

---

## Budget Configuration

Control execution limits:

```python
from mcp_agent.agent import execute_mcp_task, Budget

result = execute_mcp_task(
    task="Complex multi-step task",
    user_id="dev-local",
    budget=Budget(
        max_steps=20,           # Maximum planning steps
        max_tool_calls=50,      # Maximum tool invocations
        max_code_runs=10,       # Maximum sandbox executions
        max_llm_cost_usd=1.0,   # Maximum LLM cost
    )
)
```

**Default Budget:**
- max_steps: 10
- max_tool_calls: 30
- max_code_runs: 5
- max_llm_cost_usd: 0.5

---

## Development Workflow

### Typical Development Cycle

1. **Add/modify tool wrapper** in `mcp_agent/actions/wrappers/`
2. **Update output schemas** in `tool_output_samples.yaml`
3. **Regenerate schemas**: `./scripts/generate_tool_output_schemas.py`
4. **Test with dev script**: `./scripts/run_dev_mcp_task.py`
5. **Verify tool discovery**: Check search results include new tool
6. **Test in sandbox**: Ensure sandbox helpers work correctly

### Debugging Tips

#### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Inspect Tool Discovery

```python
from mcp_agent.knowledge.index import get_index

index = get_index("dev-local")
spec = index.get_tool("gmail.gmail_search")
print(spec.to_dict())
```

#### Test MCP Client Directly

```python
from mcp_agent.core.context import AgentContext
from mcp_agent.registry.crud import get_mcp_client

ctx = AgentContext.create("dev-local")
client = get_mcp_client(ctx, "gmail")

result = await client.acall("GMAIL_SEARCH", {
    "query": "is:unread",
    "max_results": 1
})
print(result)
```

#### Inspect Agent State

```python
# Add breakpoint in run_loop.py
import pdb; pdb.set_trace()

# Inspect state
print(f"Steps taken: {state.budget_tracker.snapshot().steps_taken}")
print(f"History: {[s.type for s in state.history]}")
print(f"Tools cached: {len(state.search_results)}")
```

---

## Code Style

### Conventions

- **Type hints**: Required for all function parameters and returns
- **Docstrings**: Required for all public functions (Google style)
- **Error handling**: Wrap MCP calls with try/except, return structured errors
- **Logging**: Use `emit_event()` for telemetry, `logger` for debug

### Example Well-Formed Wrapper

```python
from typing import Optional
from mcp_agent.actions.core import mcp_action, ToolInvocationResult
from mcp_agent.knowledge.schema_store import tool_output_schema

@tool_output_schema(
    schema={
        "messages": "array",
        "resultSizeEstimate": "integer",
    },
    pretty="""
messages[].messageId: string
messages[].subject: string
messages[].sender: string
resultSizeEstimate: integer
    """.strip()
)
@mcp_action
def gmail_search(
    self,
    query: str,
    max_results: int = 20,
    include_payload: Optional[bool] = None,
) -> ToolInvocationResult:
    """
    Search Gmail messages using Gmail query syntax.

    Args:
        query: Gmail search query (e.g., "is:unread from:john@example.com")
        max_results: Maximum number of messages to return (default: 20)
        include_payload: Include full message payloads (default: False)

    Returns:
        ActionResponse with messages array and result count
    """
    tool_name = "GMAIL_SEARCH"
    payload = {
        "query": query,
        "max_results": max_results,
    }
    if include_payload is not None:
        payload["include_payload"] = include_payload

    return self._invoke_mcp_tool("gmail", tool_name, payload)
```

---

## Running Tests (Historical)

> **Note:** The tests/ directory has been removed as part of the cleanup. Tests can be rebuilt later if needed. For now, use the scripts in scripts/ for testing.

Historical test structure:
- Unit tests: `tests/mcp_core/`, `tests/actions/`
- Integration tests: `tests/planner/`
- Sandbox tests: `tests/sandbox/`

### Rebuilding Tests (Future)

If tests are rebuilt, use pytest:

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest tests/

# Run specific test file
pytest tests/planner/test_integration_e2e.py

# Run with coverage
pytest --cov=mcp_agent tests/
```

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) - Frontend integration
- [../README.md](../README.md) - Repository overview
