# Planner Runtime Cleanup Plan

Finish decomposing the legacy planner so that state, execution, and orchestration are cleanly separated and no component depends on filesystem-generated artifacts.

## Guiding Objectives
- The knowledge layer must only introspect in memory (no JSON manifests on disk).
- `AgentState` becomes the sole in-memory record of planner progress; no more `PlannerContext`.
- `ActionExecutor` is the only component that performs work. The orchestrator just loops, calls the LLM, parses commands, and hands them to the executor.
- `planner.py` shrinks to an `AgentOrchestrator` class (<150 lines) that wires everything together.
- All references to `PlannerContext`, stub sandbox helpers, or manifest persistence disappear from both runtime code and tests.

## Phase 0 – Baseline & Safety
- [ ] Scan for any remaining imports of `planner.context` / `PlannerContext` / `planner.runtime` across `mcp_agent` and `tests/` so we know every consumer that must move to the new abstractions.
- [ ] Capture the current behaviour by running representative planner tests (at least `pytest tests/planner/test_runtime.py -k finish` and `pytest tests/planner/test_context.py`) before touching code so regressions are easy to spot later.

## Phase 1 – Remove Filesystem Persistence From `knowledge.builder`
1. **Inline manifest builders (no disk writes).**
   - [x] Delete `ToolboxBuilder.persist`, `_write_existing_manifest`, `refresh_manifest`, and all imports of `write_json_if_changed`, `write_text_if_changed`, and `safe_filename` in `mcp_agent/knowledge/builder.py`.
   - [x] Update `_MANIFEST_CACHE` entries so they only retain the manifest + fingerprint; remove `base_dir`/`persisted` bookkeeping.
2. **Rework public helpers.**
   - [x] Make `get_manifest` always call `ToolboxBuilder.build` (respecting `_MANIFEST_CACHE`), drop the `persist` flag entirely, and ensure callers treat the manifest as an in-memory object.
   - [x] Simplify `get_index` to call `ToolboxIndex.from_manifest` without touching the filesystem; delete `default_toolbox_root()` references that only existed for persistence.
3. **Verification.**
   - [x] Grep the repo for `write_json_if_changed`/`manifest.json` references to confirm nothing else tries to emit files.
   - [ ] Run any tests that covered `knowledge.builder` (`pytest tests/planner/test_context.py -k manifest`) to ensure they pass without the persisted artifacts.

## Phase 2 – Consolidate State Into `AgentState`
1. **Expand the dataclass.**
   - [x] Add fields to `mcp_agent/agent/state.py` so it tracks everything the old `PlannerContext` owned: `inventory_view` (provider tree), `discovered_tools`, search results, tool/sandbox summaries, logs, `extra_context`, and run identifiers.
   - [x] Port helper methods (`merge_search_results`, `_slim_tool_for_planner`, `_slim_provider_tree`, summary helpers, `record_event`) from `context.py` either into `AgentState` or a small companion module (e.g., `agent/state_helpers.py`).
2. **Prompt state rendering.**
   - [x] Implement `AgentState.build_planner_state()` that mirrors the JSON produced by `PlannerContext.build_planner_state` so `PlannerLLM` can consume it directly.
   - [x] Update `mcp_agent/agent/llm.py` to accept `AgentState` instead of `PlannerContext`, adjust budget snapshot plumbing, and make sure telemetry (`record_event`, token tracking, budget updates) uses the new state.
3. **Surface-level callers.**
   - [x] Replace every usage of `PlannerContext` in `mcp_agent/agent/*` (entrypoint, tests, llm, parser helpers) with `AgentState` + `AgentContext`. Keep the public API (`execute_mcp_task`) stable by constructing the new state internally.
   - [x] Stop re-exporting `PlannerContext` from `mcp_agent/agent/__init__.py` so new callers adopt `AgentState`.
   - [x] Mirror `PlannerContext` into an `AgentState` inside `PlannerRuntime` and feed that state to `PlannerLLM`/`ActionExecutor` so downstream code sees consistent data.
4. **Validation.**
   - [ ] Re-run planner context tests (now targeting `AgentState`) to confirm `build_planner_state` and summary trimming logic still behave the same. *(Ready: suite now imports `mcp_agent.agent` — just re-run `pytest tests/planner/test_context.py`.)*

## Phase 3 – Finish `ActionExecutor`
1. **Introduce a typed result.**
   - [x] Create a `StepResult` dataclass in `mcp_agent/agent/types.py` (before touching the executor) with `success`, `type`, `observation`, `preview`, `error`, and `raw_output_key`.
2. **Single entrypoint.**
   - [x] Replace `execute_action(action_type, action_input)` with `execute_step(command: Dict[str, Any]) -> StepResult`, where `command` is exactly what the parser returns.
3. **Search/tool/sandbox logic.**
   - [x] Move the bodies of `_execute_search`, `_execute_tool`, `_execute_sandbox`, `_execute_finish`, `_execute_fail` out of `planner.py` into `ActionExecutor`, ensuring:
        - Search results populate `AgentState` caches (inventory view, discovered tool specs).
        - Tool execution refuses to run unless `agent_state.has_discovered_tool(tool_id)` is true.
        - Sandbox execution reuses `_smart_format_observation` and stores logs/raw outputs on the state.
        - Finish/fail mark the state terminal and attach summaries.
4. **Budget + telemetry.**
   - [x] Ensure every branch updates the `BudgetTracker`, appends raw outputs/logs to `AgentState`, and records executor-level telemetry.
5. **Tests + guard rails.**
   - [ ] Add/adjust executor-focused tests (e.g., `tests/planner/test_runtime.py` replacements) that call `ActionExecutor.execute_step` with scripted commands to verify search enforcement and payload sanitization. *(In progress: `tests/planner/test_runtime.py` now targets `AgentOrchestrator`; remaining suites still need migration.)*

## Phase 4 – Replace `PlannerRuntime` With `AgentOrchestrator`
1. **Class + file rename.**
   - [x] Rename `PlannerRuntime` to `AgentOrchestrator` (either keep it in `mcp_agent/agent/planner.py` or split into `orchestrator.py`), keeping the public `execute_mcp_task` API the same.
2. **Loop rewrite.**
   - [x] Implement a compact `run()`:
        1. Instantiate `AgentContext`/`AgentState` (seeded with task/user/budget/extra_context).
        2. Load `inventory_view = knowledge.views.get_inventory_view(context)` into the state.
        3. Initialize a single `ActionExecutor`.
        4. While the budget allows and the state isn’t terminal:
            - Ask `PlannerLLM.generate(state)` for the next command.
            - Parse it with `parser.parse_planner_command`.
            - Send the command to `executor.execute_step`.
            - Record the observation & budget consumption on the state.
            - Handle parser/LLM errors by appending failure steps instead of raising.
3. **Result packaging.**
   - [x] Rewrite `execute_mcp_task` to build the `AgentOrchestrator`, call `run()`, and translate the final `AgentState` into the existing `MCPTaskResult` contract (final summary, budget snapshot, logs, steps, raw outputs).
4. **Helper cleanup.**
   - [x] Drop `_execute_*`, `_ensure_llm_enabled`, and other private helpers that only existed because of `PlannerContext`. Keep reusable utilities (e.g., `_smart_format_observation`) either in `executor.py` or a shared `agent/utils.py`.
5. **Acceptance checks.**
   - [x] Confirm `planner.py` is now a thin re-export (<150 lines) that simply wires in the `AgentOrchestrator` implementation housed in `orchestrator.py`, with no execution-specific logic beyond the ReAct loop.

## Phase 5 – Delete `PlannerContext` and Legacy Modules
1. **Remove `mcp_agent/agent/context.py`.**
   - [x] Delete the file once every consumer has moved to `AgentState`. Extract any still-needed helpers (redaction, summarizers) before deletion.
2. **Update exports + docs.**
   - [x] Adjust `mcp_agent/agent/__init__.py`, `entrypoint.py`, and any README/plan documents so they no longer export or mention `PlannerContext`/`PlannerRuntime`.
3. **Tests + fixtures.**
   - [x] Rewrite the `tests/planner` suite to instantiate `AgentState`/`AgentOrchestrator` directly. Remove fixtures that relied on `PlannerContext` JSON files. *(Completed: all suites now import from `mcp_agent.agent`.)*
4. **Dead code sweep.**
   - [x] Search for any `from mcp_agent.planner` imports (old namespace) and delete/migrate those files or tests.

## Phase 6 – Validation & Regression Testing
- [ ] Run `pytest tests/planner` (or the narrowed set once reorganized) to cover parser/executor/orchestrator flows. *(Blocked: missing `mcp_agent.agent.discovery` and `mcp_agent.toolbox` modules in this environment.)*
- [ ] Run `python -m compileall mcp_agent` to catch syntax regressions after the large refactor.
- [ ] Execute an end-to-end smoke test via `python -m mcp_agent.agent.entrypoint` (or the existing CLI) with a trivial task to ensure the orchestrator, executor, and sandbox/tool layers work together.
- [ ] Document any follow-up debt discovered during testing in `REFACTOR_SUMMARY.md`.

Following this plan will remove the filesystem IO, eliminate `PlannerContext`, and leave us with a clean `AgentState` + `ActionExecutor` + `AgentOrchestrator` architecture that is easier to reason about and extend.
