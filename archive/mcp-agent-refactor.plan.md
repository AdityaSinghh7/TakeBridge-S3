<!-- 4d7ccf09-9e0a-43c8-a668-c22fb8a587f8 ada89db6-7c13-4e44-a56b-4c222cc1db6b -->
# MCP Agent Architecture Refactor: ReAct/Discovery-First

## Overview

Transform the mcp_agent codebase into a clean, modular architecture with 6 logical modules that map to distinct responsibilities. Migrate incrementally, maintaining compatibility via shim layers.

## Architecture Principles

1. **user_id = tenant**: Treat `user_id` as the tenant/account identifier throughout
2. **Discovery-First Flow**: Provider tree → Search → Detailed specs → Tool/Sandbox execution
3. **Slim Payloads**: Aggressively debloat MCP responses, keep only essentials
4. **No Global State**: Pass `AgentContext` explicitly everywhere
5. **Incremental Migration**: New structure alongside old, delete old code as we migrate

---

## Phase 1: Core Foundation (Req 9)

### 1.1 Create Core Module

**Create: `mcp_agent/core/context.py`**

- Define `AgentContext` dataclass:
    - Fields: `user_id` (tenant), `request_id`, `db_session` (from shared.db.engine)
    - Method: `get_db()` - returns scoped session
- **Eliminate**: Global `_current_user_id`, `TB_USER_ID` lookups
- **Migrate from**: `mcp_agent/user_identity.py` (keep `normalize_user_id` utility only)

**Create: `mcp_agent/core/exceptions.py`**

- Define standard exception hierarchy:
    - `MCPAgentError` (base)
    - `ProviderNotFoundError`
    - `ToolNotFoundError`
    - `UnauthorizedError`
    - `ToolExecutionError`

### 1.2 Update Existing Files

**Keep minimal: `mcp_agent/user_identity.py`**

- Retain only: `normalize_user_id(user_id: str) -> str`
- Delete: `require_env_user_id`, `ensure_user_id`, `_current_user_id` logic

---

## Phase 2: Registry Layer (Req 1.5) - Source of Truth

### 2.1 Database Models Migration

**Create: `mcp_agent/registry/models.py`**

- **Migrate from**: `shared/db/models.py` - move these tables:
    - `User` (id, created_at)
    - `AuthConfig` (id, provider, name, config_json)
    - `ConnectedAccount` (id, user_id, auth_config_id, provider, status, provider_uid)
    - `MCPConnection` (id, connected_account_id, mcp_url, mcp_headers, last_error, last_sync)
- Add SQLAlchemy relationships for easy traversal
- Keep models in `mcp_agent/registry/` as source of truth for provider/tool metadata

**Create: `mcp_agent/registry/crud.py`**

- **Migrate from**: `shared/db/crud.py` - move these functions:
    - `upsert_user`, `upsert_auth_config`, `upsert_connected_account`, `upsert_mcp_connection`
    - `get_active_mcp_for_provider`, `get_active_context_for_provider`
    - `disconnect_provider`, `is_authorized`
- Update signatures to accept `AgentContext` instead of bare `user_id`

### 2.2 OAuth & Availability Manager

**Create: `mcp_agent/registry/oauth.py`**

- **Migrate from**: `mcp_agent/oauth.py` (659 lines - keep essentials, remove bloat)
- **Keep**:
    - `OAuthManager` class with these methods:
        - `start_oauth(context, provider, redirect_uri) -> str`
        - `finalize_connected_account(context, provider, ca_id) -> dict`
        - `disconnect(context, provider) -> None`
        - `is_authorized(context, provider) -> bool`
    - Token refresh and MCP URL generation logic
    - Composio API integration helpers
- **Remove**:
    - In-memory `_store` dict (use DB as source of truth)
    - `consume_redirect_hint`, `set_redirect_hints` (move to web layer if needed)
    - Legacy `handle_callback` (no-op method)
- **Update**: All methods accept `AgentContext` as first param

**Create: `mcp_agent/registry/manager.py`**

- New unified registry manager:
    - `RegistryManager(context: AgentContext)`
    - Methods:
        - `get_available_providers() -> List[ProviderInfo]` - checks DB for configured providers
        - `get_provider_tools(provider: str) -> List[ToolInfo]` - lists tools for a provider
        - `check_availability(provider: str, tool: str) -> tuple[bool, str]` - returns (is_available, reason)
        - `get_mcp_client(provider: str) -> MCPClient` - instantiates client with headers
- **Replaces**: Current `registry.py` global dict logic
- Uses `crud.py` to query DB state

### 2.3 MCP Client Wrapper

**Keep: `mcp_agent/mcp_client.py`** (already clean, ~115 lines)

- Minor update: Accept headers dict in constructor (no registry access)
- Remove registry coupling, make it a pure HTTP client

### 2.4 Delete Old Registry

**Delete: `mcp_agent/registry.py`** (after migration complete)

- Global `MCP_BY_USER` dict removed
- `init_registry`, `get_client`, `is_registered` replaced by `RegistryManager`

---

## Phase 3: Actions Layer (Req 1) - The Hands

### 3.1 Standardize Action Wrappers

**Refactor: `mcp_agent/actions.py`** (currently 781 lines - split into modules)

**Create: `mcp_agent/actions/wrappers/gmail.py`**

- Extract from `actions.py`:
    - `gmail_send_email(context, to, subject, body, ...)` 
    - `gmail_search(context, query, max_results, ...)`
- **Update signature**: Accept `AgentContext` as first param (not `self`)
- **Keep**: Parameter mapping logic (to → recipient_email)
- **Remove**: `@tool_output_schema` decorators for metadata (We get output schemas from @tool_output_schemas.generated.json using the @build_tool_output_schema.py script)
- **Remove**: `_validation_only` checks (move to test layer)
- **Remove**: Direct `OAuthManager.is_authorized` calls (use `context.registry`)

**Create: `mcp_agent/actions/wrappers/slack.py`**

- Extract from `actions.py`:
    - `slack_post_message(context, channel, text, ...)`
    - `slack_search_messages(context, query, count, ...)`
- Same updates as gmail

**Create: `mcp_agent/actions/dispatcher.py`**

- Central routing:
    - `dispatch_tool(context, provider, tool, payload) -> ActionResponse`
    - Maps `(provider, tool)` to wrapper function
    - Validates availability via `context.registry.check_availability()`
    - Returns normalized `ActionResponse` envelope

**Keep: `mcp_agent/actions/__init__.py`**

- Export:
    - `get_provider_action_map() -> dict[str, tuple[Callable, ...]]`
    - `dispatch_tool` from dispatcher
- **Remove exports**: Internal helpers like `_invoke_mcp_tool`, `_current_user_id`

### 3.2 Action Response Envelope (already in toolbox)

**Keep: `mcp_agent/toolbox/envelope.py`** (131 lines - already clean)

- `normalize_action_response(raw) -> ActionResponse`
- **Migrate to**: `mcp_agent/execution/envelope.py` (Phase 5)

---

## Phase 4: Knowledge Layer (Req 2, 3, 4) - The Brain

### 4.1 Metadata Builder

**Refactor: `mcp_agent/toolbox/builder.py`** (409 lines)

- **Migrate to**: `mcp_agent/knowledge/builder.py`
- **Keep**:
    - `ToolboxBuilder` class
    - `get_manifest(context)` - builds full metadata
    - `get_index(context)` - returns searchable index
    - Introspection logic (parameters, docstrings, output schemas)
- **Update**:
    - Accept `AgentContext` instead of `user_id` string
    - Use `context.registry.check_availability()` for `available` flags
- **Remove**:
    - `_MANIFEST_CACHE` in-memory dict (use DB or generate on-demand)
    - `persist()` method (toolbox generation should be ephemeral)

**Create: `mcp_agent/knowledge/schema_store.py`**

- Caching layer for tool schemas:
    - `get_tool_schema(context, provider, tool) -> dict` - returns JSON schema
    - Cache key: `f"{context.user_id}:{provider}:{tool}"`
    - TTL: 5 minutes (refresh if registry version changes)
- **Migrate from**: `mcp_agent/toolbox/output_schema_loader.py` logic

### 4.2 View Generators (Req 3)

**Create: `mcp_agent/knowledge/views.py`**

- **Two views for ReAct flow**:

**View 1: Inventory (Req 3A - Initial State)**

```python
def get_inventory_view(context: AgentContext) -> dict:
    """
    Returns slim provider tree: provider names + tool names only.
    
    Output:
    {
        "providers": [
            {"provider": "gmail", "tools": ["gmail_send_email", "gmail_search"]},
            {"provider": "slack", "tools": ["slack_post_message", "slack_search_messages"]}
        ]
    }
    """
```

**View 2: Deep View (Req 3B - Post-Search)**

```python
def get_deep_view(context: AgentContext, tool_ids: list[str]) -> list[dict]:
    """
    Returns detailed specs for specific tools discovered via search.
    
    Output (DEBLOATED):
    [
        {
            "tool_id": "gmail.gmail_search",
            "description": "...",
            "input_params": {"required": [...], "optional": [...]},
            "output_fields": ["messages[].messageId", "messages[].subject", ...],
            "call_signature": "gmail.gmail_search(query, max_results)"
        }
    ]
    
    REMOVED from output:
  - raw docstrings
  - source paths
  - py_module/py_name (internal)
  - verbose output_schema (replaced with flat output_fields)
    """
```

- **Migrate from**: 
    - `mcp_agent/planner/discovery.py` → `load_provider_topology` becomes inventory view
    - `mcp_agent/toolbox/search.py` → `search_tools` becomes search + deep view

### 4.3 Search Engine (Req 4)

**Refactor: `mcp_agent/toolbox/search.py`** (178 lines)

- **Migrate to**: `mcp_agent/knowledge/search.py`
- **Keep**:
    - `search_tools(context, query, limit) -> list[dict]` - semantic scoring
    - `_score_tool(tool, query)` - keyword matching logic
    - Provider filtering to prevent cross-contamination
- **Update**:
    - Return results from `get_deep_view()` (debloated format)
    - Use `context.registry` for availability checks
    - Remove `detail_level` param (always return deep view)
- **Remove**:
    - `list_providers()` - replaced by `get_inventory_view()`

### 4.4 Cleanup Toolbox

**Delete after migration**:

- `mcp_agent/toolbox/builder.py` → moved to knowledge/
- `mcp_agent/toolbox/search.py` → moved to knowledge/
- `mcp_agent/toolbox/envelope.py` → moved to execution/
- `mcp_agent/toolbox/registry.py` → replaced by registry/manager.py
- `mcp_agent/toolbox/docstring_specs.py` → keep if used by builder
- `mcp_agent/toolbox/python_generator.py` → DELETE (no sandbox_py generation needed)

**Keep (if actively used)**:

- `mcp_agent/toolbox/models.py` - data classes
- `mcp_agent/toolbox/index.py` - index structures
- `mcp_agent/toolbox/utils.py` - utilities

---

## Phase 5: Execution Layer (Req 5, 7) - The Runtime

### 5.1 Slim Envelope (Req 5)

**Migrate: `mcp_agent/toolbox/envelope.py` → `mcp_agent/execution/envelope.py`**

- Already clean (131 lines)
- **Enhance**: Add aggressive truncation
    - `process_observation(context, raw_response, metadata) -> dict`
    - Truncate strings > 500 chars to 500 + "..."
    - Truncate arrays > 20 items to first 20 + {"truncated": true, "total": N}
    - Flatten nested objects beyond depth 3

### 5.2 Sandbox Integration (Req 7)

**Refactor: `mcp_agent/sandbox/runner.py`** (173 lines)

- **Migrate to**: `mcp_agent/execution/sandbox.py`
- **Keep**:
    - `run_python_plan(context, code, timeout)` - subprocess execution
    - Environment setup (PYTHONPATH, TB_USER_ID)
    - Result parsing
- **Update**:
    - Accept `AgentContext` instead of `user_id` string
    - Inject context into sandbox globals (not env vars)
- **Remove**:
    - Temporary directory persistence (always ephemeral)

**Keep: `mcp_agent/sandbox/glue.py`**

- Already clean, provides MCP tool caller for sandbox

---

## Phase 6: Agent Layer (Req 6, 8) - The Soul

### 6.1 Planner/Runtime

**Refactor: `mcp_agent/planner/runtime.py`** (805 lines - MAJOR DEBLOAT)

**Keep**:

- `PlannerRuntime` class
- `execute_mcp_task(task, context) -> MCPTaskResult` - entry point
- ReAct loop: `_next_command() → _dispatch_command() → [tool|search|sandbox]`
- Budget tracking and policy enforcement

**Update**:

- Use `knowledge.views.get_inventory_view()` for initial provider tree
- Use `knowledge.search.search_tools()` for discovery
- Use `execution.envelope.process_observation()` for response slimming
- Use `actions.dispatcher.dispatch_tool()` for tool execution

**Remove**:

- `_smart_format_observation` - replace with `process_observation` from envelope
- Direct imports from `toolbox.*` - use new module structure
- Wrapper function routing logic (lines 502-516) - use dispatcher instead

**Migrate to**: `mcp_agent/agent/planner.py`

### 6.2 Context & State

**Refactor: `mcp_agent/planner/context.py`** (716 lines)

- **Keep**:
    - `PlannerContext` dataclass (core state)
    - `build_planner_state()` - trajectory building
    - Step recording and history
- **Update**:
    - Embed `AgentContext` as field
    - Use `_slim_tool_for_planner()` for ALL search results (enforce debloat)
- **Remove**:
    - `_search_index` in-memory dict (use list only)
    - Summarization logic (move to execution/envelope.py)
    - `_persist_summaries` persistence logic

**Migrate to**: `mcp_agent/agent/context.py`

### 6.3 Prompts

**Keep: `mcp_agent/planner/prompt.py`**

- **Migrate to**: `mcp_agent/agent/prompts.py`
- **Update**: Enforce "Search First" rule in system prompt
- **Clarify**: Inventory view vs. Deep view distinction

### 6.4 Supporting Files

**Keep and migrate**:

- `mcp_agent/planner/llm.py` → `mcp_agent/agent/llm.py`
- `mcp_agent/planner/parser.py` → `mcp_agent/agent/parser.py`
- `mcp_agent/planner/budget.py` → `mcp_agent/agent/budget.py`
- `mcp_agent/planner/actions.py` → DELETE (replace with actions/dispatcher.py)
- `mcp_agent/planner/discovery.py` → DELETE (replace with knowledge/views.py)

### 6.5 Entry Point

**Create: `mcp_agent/agent/entrypoint.py`**

- Public API:
```python
def execute_task(
    task: str,
    user_id: str,
    budget: Budget | None = None
) -> MCPTaskResult:
    """
    Main entry point for MCP task execution.
    
    Flow:
  1. Initialize AgentContext (user_id, db_session, registry)
  2. Create PlannerRuntime
  3. Load inventory view (provider tree)
  4. Run ReAct loop until completion
  5. Return strict MCPTaskResult
    """
```


**Migrate from**: `mcp_agent/planner/runtime.py:execute_mcp_task()`

---

## Phase 7: Compatibility & Cleanup

### 7.1 Compatibility Shim

**Create: `mcp_agent/compat.py`**

- Backward-compatible wrappers for:
    - `from mcp_agent.registry import init_registry, get_client` → proxy to new RegistryManager
    - `from mcp_agent.oauth import OAuthManager` → proxy to registry.oauth
    - `from mcp_agent.toolbox.builder import get_manifest` → proxy to knowledge.builder
- Mark all as `@deprecated` with migration hints

### 7.2 Update Public API

**Update: `mcp_agent/__init__.py`**

```python
# New clean exports
from .agent.entrypoint import execute_task
from .core.context import AgentContext
from .core.exceptions import MCPAgentError
from .registry.manager import RegistryManager

# Legacy compatibility (deprecated)
from .compat import (
    init_registry,  # deprecated: use RegistryManager
    get_client,     # deprecated: use RegistryManager.get_mcp_client
    OAuthManager,   # deprecated: use registry.oauth
)
```

### 7.3 Update External Callers

**Files to update**:

- `server/api/*.py` - update to use new `execute_task` entry point
- `computer_use_agent/tools/mcp_*.py` - update imports via compat layer initially

### 7.4 Delete Obsolete Files

**After full migration**:

- `mcp_agent/registry.py` ✓
- `mcp_agent/oauth.py` ✓ (moved to registry/)
- `mcp_agent/actions.py` ✓ (split into wrappers/)
- `mcp_agent/mcp_agent.py` ✓ (replaced by agent/entrypoint.py)
- `mcp_agent/toolbox/` ✓ (migrated to knowledge/ and execution/)
- `mcp_agent/planner/` ✓ (migrated to agent/)
- `mcp_agent/sandbox/` ✓ (migrated to execution/)

---

## Success Criteria

1. ✅ No global state (all functions accept `AgentContext`)
2. ✅ Clean module boundaries (6 distinct layers)
3. ✅ Debloated payloads (slim envelope everywhere)
4. ✅ Discovery-first flow (inventory → search → deep view → execution)
5. ✅ DB as source of truth (no in-memory caches)
6. ✅ Backward compatibility (via shim layer)
7. ✅ All tests passing with new structure

---

## Final Directory Structure

```
mcp_agent/
├── core/
│   ├── __init__.py
│   ├── context.py          # AgentContext dataclass
│   └── exceptions.py       # Standardized errors
├── registry/               # Source of truth for providers/tools
│   ├── __init__.py
│   ├── models.py          # DB schemas (migrated from shared/db)
│   ├── crud.py            # DB operations
│   ├── oauth.py           # Token management
│   └── manager.py         # RegistryManager (availability checks)
├── actions/               # Raw MCP wrappers
│   ├── __init__.py
│   ├── dispatcher.py      # Route (provider, tool) → wrapper
│   └── wrappers/
│       ├── __init__.py
│       ├── gmail.py       # Gmail action wrappers
│       └── slack.py       # Slack action wrappers
├── knowledge/             # Metadata & search
│   ├── __init__.py
│   ├── builder.py         # Build tool metadata
│   ├── schema_store.py    # Cache JSON schemas
│   ├── search.py          # Semantic tool search
│   └── views.py           # Inventory vs. Deep views
├── execution/             # I/O & sandbox
│   ├── __init__.py
│   ├── envelope.py        # Slim observation processing
│   └── sandbox.py         # Python code runner
├── agent/                 # ReAct loop
│   ├── __init__.py
│   ├── entrypoint.py      # execute_task() public API
│   ├── planner.py         # ReAct while loop
│   ├── context.py         # PlannerContext state
│   ├── prompts.py         # System prompts
│   ├── llm.py             # LLM interface
│   ├── parser.py          # Command parsing
│   └── budget.py          # Policy enforcement
├── compat.py              # Backward compatibility shim
├── user_identity.py       # Keep normalize_user_id only
├── mcp_client.py          # Keep as-is (pure HTTP client)
└── types.py               # Shared type definitions
```

**Deleted**:

- `registry.py`, `oauth.py`, `actions.py`, `mcp_agent.py`
- `toolbox/` directory (migrated)
- `planner/` directory (migrated)
- `sandbox/` directory (migrated)

### To-dos

- [ ] Phase 1: Create core module (context.py, exceptions.py)
- [ ] Phase 2.1: Migrate DB models to registry/models.py and crud.py
- [ ] Phase 2.2: Refactor oauth.py into registry/oauth.py (debloat)
- [ ] Phase 2.3: Create registry/manager.py (unified RegistryManager)
- [ ] Phase 3.1: Split actions.py into wrappers/gmail.py and wrappers/slack.py
- [ ] Phase 3.2: Create actions/dispatcher.py (central routing)
- [ ] Phase 4.1: Migrate toolbox/builder.py to knowledge/builder.py
- [ ] Phase 4.2: Create knowledge/views.py (inventory & deep views)
- [ ] Phase 4.3: Migrate toolbox/search.py to knowledge/search.py (debloat)
- [ ] Phase 5.1: Migrate toolbox/envelope.py to execution/envelope.py
- [ ] Phase 5.2: Migrate sandbox/runner.py to execution/sandbox.py
- [ ] Phase 6.1: Migrate planner/runtime.py to agent/planner.py (debloat)
- [ ] Phase 6.2: Migrate planner/context.py to agent/context.py
- [ ] Phase 6.3: Migrate planner supporting files (llm, parser, budget, prompts)
- [ ] Phase 6.4: Create agent/entrypoint.py (public API)
- [ ] Phase 7.1: Create compat.py shim layer for backward compatibility
- [ ] Phase 7.2: Update external callers (server/api, computer_use_agent)
- [ ] Phase 7.3: Delete obsolete files (old registry, oauth, actions, toolbox, planner, sandbox)