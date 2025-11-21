# Changelog

This document tracks major architectural changes and refactorings in the MCP Agent project.

---

## Repository Cleanup (2025-01-21)

**Category:** Repository Maintenance

### Changes

- **Scripts Directory Cleanup**
  - Removed 5 irrelevant scripts: `get_slack_oauth_link.py`, `orchestrate_task.py`, `probe_tool_outputs.py`, `show_triage_csv.py`, `trace_execute_mcp_task.py`
  - Moved `probe_tools.py` to `scripts/` directory
  - Retained only essential scripts: `build_tool_output_schemas.py`, `run_dev_mcp_task.py`, `generate_tool_output_schemas.py`

- **Temporary Directory Cleanup**
  - Removed 6 temporary toolbox directories: `tmp_toolbox_debug2/`, `tmp_toolbox_debug4/`, `tmp_toolbox_debug6/`, `tmp_toolbox_debug7/`, `tmp_toolbox_run2/`, `tmp_toolbox_run3/`
  - Removed root-level `toolbox/` directory (sandbox toolbox preserved at `mcp_agent/toolbox/`)

- **Test Infrastructure Removal**
  - Completely removed `tests/` directory
  - Testing now handled through scripts in `scripts/` directory

- **Documentation Consolidation**
  - Created `archive/` directory for completed planning documents
  - Consolidated scattered documentation into comprehensive guides:
    - `docs/ARCHITECTURE.md` - System architecture, 6-layer breakdown, data flow
    - `docs/INTEGRATION_GUIDE.md` - Frontend integration, OAuth, SSE streaming, API reference
    - `docs/DEVELOPMENT.md` - Development workflow, adding tools/providers, debugging
    - `docs/CHANGELOG.md` - This file
  - Archived 7 completed plan documents: `MCP_Multi_Tenant_Implementation_Plan.md`, `Standalone_MCP_Agent_Checklist.md`, `MIGRATION_COMPLETE.md`, `REFACTOR_SUMMARY.md`, `mcp-agent-refactor.plan.md`, `planner_prompt_overhaul_plan.md`, `planner_runtime_cleanup.plan.md`

### Rationale

- Reduce repository clutter and improve navigation
- Establish single source of truth for documentation
- Focus testing on practical scripts rather than outdated unit tests
- Preserve historical planning documents in archive

---

## Phase 1: Agent Layer Consolidation (2025-01)

**Category:** Architectural Refactoring

### Changes

- **File Consolidation**
  - Merged `mcp_agent/agent/planner.py` → `mcp_agent/agent/orchestrator.py` → `mcp_agent/agent/run_loop.py`
  - Single unified planning loop in `run_loop.py`
  - Removed duplicate orchestration logic

- **Main Entrypoint**
  - `execute_mcp_task()` function as primary API
  - Legacy aliases preserved for backward compatibility: `AgentOrchestrator`, `PlannerRuntime`

### Files Modified

- `mcp_agent/agent/run_loop.py` - New unified planning loop
- `mcp_agent/agent/__init__.py` - Updated exports
- Deleted: `mcp_agent/agent/planner.py`, `mcp_agent/agent/orchestrator.py`

### Rationale

- Eliminate code duplication between planner/orchestrator
- Simplify agent layer to single responsibility
- Improve maintainability and debugging

---

## Phase 6: AgentState Decomposition (2025-01)

**Category:** Architectural Refactoring

### Changes

- **Extracted Components from Monolithic AgentState**
  - `ExecutionHistory` (mcp_agent/agent/history.py) - Step tracking and history management
  - `ToolCache` (mcp_agent/agent/tool_cache.py) - Tool search result caching
  - `SummaryManager` (mcp_agent/agent/summary_manager.py) - Conversation summarization

- **AgentState Simplification**
  - Reduced to core state: context, budget tracker, history, tool cache, summary manager
  - Clear separation of concerns
  - Better testability and composability

### Files Added

- `mcp_agent/agent/history.py` - ExecutionHistory, AgentStep, StepType
- `mcp_agent/agent/tool_cache.py` - ToolCache with TTL and scoring
- `mcp_agent/agent/summary_manager.py` - Conversation summarization logic

### Files Modified

- `mcp_agent/agent/state.py` - Simplified AgentState
- `mcp_agent/agent/__init__.py` - Updated exports

### Rationale

- Break up 500+ line AgentState class
- Improve code organization and reusability
- Make individual components testable in isolation
- Reduce cognitive load when working with agent state

---

## Multi-Tenant OAuth Implementation (2024-12)

**Category:** Feature Addition

### Changes

- **Per-User OAuth Connections**
  - Database-backed OAuth state storage (`server/models.py`)
  - User-specific MCP client registry (`mcp_agent/registry/`)
  - OAuth manager for authorization flows (`mcp_agent/registry/oauth.py`)

- **Multi-User Support**
  - Each user maintains independent OAuth connections
  - Isolated tool access per user
  - User-specific tool discovery indexes

### New Modules

- `mcp_agent/registry/oauth.py` - OAuth flow management
- `mcp_agent/registry/crud.py` - MCP client creation/retrieval
- `mcp_agent/registry/models.py` - OAuth connection models
- `server/models.py` - Database models for connections/users

### Rationale

- Enable SaaS-style multi-tenant deployments
- Secure per-user credential isolation
- Support multiple users with different tool permissions

---

## Standalone MCP Agent Creation (2024-12)

**Category:** Major Architectural Change

### Changes

- **6-Layer Architecture**
  - Layer 0: Shared Infrastructure (logger, streaming, cost tracking)
  - Layer 1: MCP Core (mcp_client, registry, oauth)
  - Layer 2: Action Wrappers (gmail, slack providers)
  - Layer 3: Knowledge & Tool Discovery (index, search, introspection)
  - Layer 4: Sandbox Execution (ephemeral environments, glue, runner)
  - Layer 5: Agent Orchestration (run loop, state, executor, LLM)

- **ReAct Planning Loop**
  - Think → Act → Observe cycle
  - LLM-guided decision making
  - Budget-constrained execution

- **Ephemeral Sandbox Execution**
  - Isolated Python environments per execution
  - Generated `sandbox_py` modules with tool helpers
  - Automatic cleanup after execution

- **Tool Discovery System**
  - Introspection of Python wrapper functions
  - Search-based tool discovery via embeddings
  - Structured parameter and output schema documentation

### Key Files

- `mcp_agent/agent/run_loop.py` - Main planning loop
- `mcp_agent/sandbox/ephemeral.py` - Ephemeral environment management
- `mcp_agent/knowledge/search.py` - Tool search API
- `mcp_agent/actions/core.py` - ActionProvider base class

### Rationale

- Decouple agent logic from TakeBridge server
- Enable standalone usage and testing
- Improve modularity and maintainability
- Support flexible deployment models (embedded, microservice, CLI)

---

## Documentation Notes

For detailed information on any of these changes, see:
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System design and layer breakdown
- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) - Frontend integration patterns
- [DEVELOPMENT.md](./DEVELOPMENT.md) - Development workflow and tool addition

Archived planning documents are available in `archive/` for historical reference.
