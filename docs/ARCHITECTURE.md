# MCP Agent Architecture

This document describes the architecture of the standalone MCP (Model-Context-Protocol) Agent system.

## Overview

The MCP Agent is a **fully autonomous Python agent** that:
- Accepts natural language task descriptions
- Discovers available tools dynamically
- Plans and executes multi-step workflows
- Runs tools via MCP providers (Gmail, Slack, etc.)
- Executes arbitrary Python code in sandboxed environments
- Returns structured results with budget tracking

**Key Principle:** Provider-agnostic architecture - adding new integrations only requires updating action wrappers and regenerating toolbox artifacts.

---

## Layered Architecture

### Layer 0: Shared Infrastructure

**Location:** `shared/` package

Cross-cutting utilities used across the system:

- **`shared/token_cost_tracker.py`** - LLM token cost tracking with budget enforcement
- **`shared/logger.py`** - Unified logging infrastructure
- **`shared/llm_client.py`** - Provider-agnostic LLM facade (OpenAI/DeepSeek/OpenRouter routing)
- **`shared/oai_client.py`** - OpenAI Responses API client
- **`shared/deepseek_client.py`** - DeepSeek Chat Completions client
- **`shared/openrouter_client.py`** - OpenRouter Chat Completions client
- **`shared/streaming.py`** - Event emission for streaming updates

All LLM invocations and telemetry go through these shared modules.

**LLM routing knobs (env):**
- `LLM_PROVIDER=openai|deepseek|openrouter` (default: `openai`)
- `LLM_MODEL=o4-mini` (optional default OpenAI model)
- `DEEPSEEK_API_KEY=...` (required for DeepSeek)
- `DEEPSEEK_BASE_URL=https://api.deepseek.com` (optional override)
- `DEEPSEEK_MODEL=deepseek-reasoner` (optional override)
- `OPENROUTER_API_KEY=...` (required for OpenRouter)
- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1` (optional override)
- `OPENROUTER_MODEL=qwen/qwen3-vl-235b-a22b-instruct` (optional override)
- `OPENROUTER_HTTP_REFERER=...` (optional header for OpenRouter ranking)
- `OPENROUTER_TITLE=...` (optional header for OpenRouter ranking)
- `LLM_IMAGE_PROVIDER=openrouter` (optional; route image content from DeepSeek to a multimodal provider)
- `LLM_FALLBACK_PROVIDER=openai` (optional; use when DeepSeek hits unsupported Responses API features)

### Layer 1: MCP Core

**Location:** `mcp_agent/` core modules

Provider-neutral MCP infrastructure:

- **`mcp_client.py`** - HTTP MCP client for calling Composio tools
- **`registry/`** - Per-user MCP client registry
  - `crud.py` - Registry CRUD operations
  - `manager.py` - Client lifecycle management
  - `oauth.py` - Composio OAuth white-label integration (DB-backed)
  - `models.py` - Database models for connections

The registry automatically refreshes when new OAuth connections are established.

### Layer 2: Action Wrappers

**Location:** `mcp_agent/actions/`

Provider-specific tool wrappers that normalize MCP calls:

- **`wrappers/gmail.py`** - Gmail actions (search, send email)
- **`wrappers/slack.py`** - Slack actions (post message, search)
- **`core.py`** - Base wrapper infrastructure
- **`registry.py`** - Action discovery and registration

**Wrapper Responsibilities:**
- Normalize arguments (handle string lists, structured payloads)
- Call MCP via registry: `get_mcp_client(context, provider).acall(...)`
- Normalize responses to `ActionResponse` envelope
- Emit telemetry events

**Adding New Tools:** New integrations are added here; the planner is NOT modified for new providers.

### Layer 3: Knowledge & Tool Discovery

**Location:** `mcp_agent/knowledge/`

Tool introspection and search capabilities:

- **`index.py`** - Tool registry and lookup
- **`introspection.py`** - Extract tool metadata from action wrappers
- **`search.py`** - Tool search and ranking
- **`types.py`** - Tool specification types

Output schemas are attached on wrappers via `mcp_agent/tool_schemas.py`.

**Discovery Flow:**
1. Introspect action wrappers to build tool specs
2. Read output schemas from wrapper `__tb_output_schema__` attributes
3. Create searchable index with full metadata
4. Expose via `search_tools(query, detail_level)` API

### Layer 4: Sandbox Execution

**Location:** `mcp_agent/sandbox/` and `mcp_agent/execution/`

Safe Python code execution environment:

- **`ephemeral.py`** - Ephemeral sandbox environment setup
- **`glue.py`** - Bridge between sandbox code and MCP tools
- **`execution/runner.py`** - Sandbox execution

**Sandbox Features:**
- Generated `sandbox_py` modules expose tools as Python functions
- Isolated execution environment per task
- Automatic error handling and timeout enforcement
- Tool call responses normalized to `{"successful": bool, "data": dict, "error": str|null}`

### Layer 5: Agent Orchestration

**Location:** `mcp_agent/agent/`

The planning and execution loop:

#### Core Components

- **`run_loop.py`** - Main agent orchestration loop
  - `AgentOrchestrator` - Coordinates planning and execution
  - `execute_mcp_task()` - Main entry point
- **`state.py`** - Agent state management (delegates to focused components)
- **`executor.py`** - Action execution (tools, sandbox, search)
- **`llm.py`** - LLM interface for planning
- **`prompts.py`** - System prompts and instructions
- **`parser.py`** - Parse LLM commands
- **`budget.py`** - Budget tracking and enforcement
- **`types.py`** - Type definitions

#### Focused State Components (Phase 6 Refactoring)

- **`history.py`** - `ExecutionHistory` class
  - Step recording and trajectory building
  - Context window management
  - Observation summarization for LLM
- **`tool_cache.py`** - `ToolCache` class
  - Tool discovery results caching
  - Deduplication by tool ID
  - MCP tool name resolution
- **`summary_manager.py`** - `SummaryManager` class
  - Output size monitoring
  - Summarization for large payloads
  - Storage path management

**State Management Philosophy:**
- `AgentState` is a lean coordinator that delegates to focused components
- Each component has a single, well-defined responsibility
- Clear separation between state (what we remember) and logic (how we process)

#### Entry Point

```python
from mcp_agent.agent import execute_mcp_task, Budget

result = execute_mcp_task(
    task="Send an email to john@example.com with project status",
    user_id="dev-local",
    budget=Budget(max_steps=10, max_tool_calls=30),
)
```

**Result Structure (`MCPTaskResult`):**
```python
{
    "success": bool,
    "final_summary": str,
    "user_id": str,
    "run_id": str,
    "raw_outputs": dict,          # Keyed by result labels
    "budget_usage": {
        "steps_taken": int,
        "tool_calls": int,
        "code_runs": int,
        "estimated_llm_cost_usd": float,
        ...
    },
    "logs": list[dict],           # Telemetry events
    "steps": list[dict],          # Execution trajectory
    "error": str | None,
    "error_code": str | None,
    "error_message": str | None,
}
```

---

## Planning Loop Flow

1. **Initialize**
   - Create `AgentState` with task, user, budget
   - Generate ephemeral toolbox in temp directory
   - Set up ExecutionHistory, ToolCache, SummaryManager

2. **Load Provider Inventory**
   - Get high-level provider tree (Gmail, Slack, etc.)
   - Mark discovery as completed

3. **Main Loop** (until terminal state)
   - Check budget constraints
   - Ask LLM for next command (via `PlannerLLM`)
   - Parse command (search, tool, sandbox, finish, fail)
   - Execute via `ActionExecutor`:
     - **search**: Find tools matching query
     - **tool**: Call MCP tool directly
     - **sandbox**: Execute Python code with tool access
     - **finish**: Complete successfully
     - **fail**: Abort with error
   - Record step in ExecutionHistory
   - Update budget tracking

4. **Return Result**
   - Package final state into `MCPTaskResult`
   - Include trajectory, outputs, budget usage, logs

---

## Key Design Principles

### 1. Context Hygiene
- Centralized planner prompt (system-level instructions)
- Structured tool summaries (not full payloads)
- Automatic observation summarization
- Budget enforcement with cost tracking

### 2. Provider Agnosticism
- Core planner never knows about specific providers
- All provider logic in action wrappers
- Tool discovery via generic search API
- Adding tools = updating wrappers + regenerating artifacts

### 3. Safety & Isolation
- Sandbox code runs in isolated environments
- Automatic cleanup of temporary directories
- Budget limits (steps, tool calls, cost)
- Structured error handling

### 4. Observability
- Structured telemetry events via `emit_event()`
- Full execution trajectory in results
- Raw outputs stored for inspection
- LLM cost tracking per request

---

## Data Flow

```
User Request
    ↓
execute_mcp_task(task, user_id)
    ↓
AgentOrchestrator.run()
    ↓
┌─────────────────────────────────┐
│  Planning Loop                  │
│  1. LLM generates command       │
│  2. Parse command type          │
│  3. Execute via ActionExecutor  │
│  4. Record in ExecutionHistory  │
│  5. Update budget & state       │
└─────────────────────────────────┘
    ↓
┌──────────────────┬──────────────────┬────────────────┐
│  search_tools    │   MCP Tool Call  │  Sandbox Run   │
│  (Knowledge)     │   (Registry)     │  (Ephemeral)   │
└──────────────────┴──────────────────┴────────────────┘
    ↓                     ↓                   ↓
 Tool Specs          ActionResponse      Sandbox Result
    ↓                     ↓                   ↓
    └─────────────────────┴───────────────────┘
                         ↓
              Record in AgentState
                         ↓
                   MCPTaskResult
```

---

## Database Integration

The MCP Agent integrates with a PostgreSQL database for:

### OAuth Connections
**Table:** `mcp_connections`
- Stores Composio OAuth tokens per user/provider
- Managed via `OAuthManager` in `mcp_agent/registry/oauth.py`
- Automatic refresh on registry initialization

### Registry State
**Table:** `mcp_clients`
- Caches MCP client configurations per user
- Provider URLs, capabilities, metadata
- Invalidated when OAuth connections change

---

## File Structure

```
mcp_agent/
├── __init__.py           # Main exports (execute_mcp_task, AgentContext)
├── agent/                # Agent orchestration (Layer 5)
│   ├── run_loop.py       # Main orchestrator
│   ├── state.py          # State coordinator
│   ├── history.py        # ExecutionHistory
│   ├── tool_cache.py     # ToolCache
│   ├── summary_manager.py # SummaryManager
│   ├── executor.py       # Action execution
│   ├── llm.py            # LLM interface
│   ├── prompts.py        # System prompts
│   ├── budget.py         # Budget management
│   ├── parser.py         # Command parsing
│   └── types.py          # Type definitions
├── actions/              # Action wrappers (Layer 2)
│   ├── core.py           # Base wrapper
│   ├── registry.py       # Discovery
│   └── wrappers/
│       ├── gmail.py      # Gmail tools
│       └── slack.py      # Slack tools
├── knowledge/            # Tool discovery (Layer 3)
│   ├── index.py          # Tool registry
│   ├── introspection.py  # Metadata extraction
│   ├── search.py         # Tool search
│   └── types.py          # Specs
├── sandbox/              # Sandbox execution (Layer 4)
│   ├── ephemeral.py      # Environment setup
│   ├── glue.py           # Tool bridge
│   └── runtime.py         # Tool caller runtime
├── execution/            # Sandbox execution helpers
│   └── runner.py         # Execution
├── registry/             # MCP infrastructure (Layer 1)
│   ├── crud.py           # Registry operations
│   ├── manager.py        # Client management
│   ├── oauth.py          # OAuth integration
│   └── models.py         # DB models
├── core/                 # Core utilities
│   ├── context.py        # AgentContext
│   └── exceptions.py     # Error types
├── env_sync.py           # Environment setup
└── tool_schemas.py       # Output schema decorators

shared/                   # Cross-cutting (Layer 0)
├── token_cost_tracker.py
├── logger.py
├── llm_client.py
├── oai_client.py
├── deepseek_client.py
└── streaming.py

docs/                     # Documentation
├── ARCHITECTURE.md       # This file
├── INTEGRATION_GUIDE.md  # Frontend integration
└── DEVELOPMENT.md        # Dev guide
```

---

## Recent Major Changes

### Phase 6: AgentState Decomposition (Latest)
- Extracted `ExecutionHistory`, `ToolCache`, `SummaryManager` from `AgentState`
- Reduced state.py from 812 to 343 lines (57% reduction)
- Clear single responsibilities for each component
- Better testability and maintainability

### Phase 1: Agent Layer Consolidation
- Merged `planner.py` into `orchestrator.py` (renamed to `run_loop.py`)
- Deleted thin wrapper `entrypoint.py`
- Single entry point: `execute_mcp_task()`
- Cleaner agent layer architecture

### Multi-Tenant Implementation
- Per-user OAuth connections and registry state
- Database-backed connection management
- Isolated execution environments per user
- Dynamic provider discovery based on user authorizations

---

## See Also

- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) - Frontend integration patterns
- [DEVELOPMENT.md](./DEVELOPMENT.md) - Adding tools and providers
- [../README.md](../README.md) - Repository overview
