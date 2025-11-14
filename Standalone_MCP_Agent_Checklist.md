# Standalone MCP Agent Checklist

Reference checklist derived from the "Standalone MCP Agent Plan (Detailed, Python-Only)". Each checkbox is intentionally small and precise so work can be tracked incrementally.

## 1. Goals, Scope & Guardrails
- [x] Record the `execute_mcp_task(...) -> MCPTaskResult` contract (inputs, defaults, success/error schema) in `mcp_agent/planner/__init__.py` docstrings.
- [x] Define the `MCPTaskResult` TypedDict/dataclass in code and ensure every field mentioned in the plan exists (`success`, `final_summary`, `raw_outputs`, `budget_usage`, `logs`, `error`).
- [x] Document in `README.md` that the standalone planner must not import from `computer_use_agent/` and add a unit test or lint rule that asserts this.
- [x] Capture the autonomy requirements (tool discovery, sandbox usage, structured result) in developer documentation for quick reference.

## 2. Layer 0 – Shared Infrastructure Extraction
### 2.1 Token Cost Tracker
- [x] Move `computer_use_agent/utils/token_cost_tracker.py` to `shared/token_cost_tracker.py`.
- [x] Update every import across the repo to use `shared.token_cost_tracker`.
- [x] Add/adjust tests to ensure the shared tracker is initialized identically to the old location.

### 2.2 Logger
- [x] Identify the current logger utilities under `computer_use_agent/`.
- [x] Move the logger module into `shared/logger.py` without breaking existing behavior.
- [x] Update imports across `computer_use_agent`, `mcp_agent`, and any other packages to use the shared logger.
- [x] Verify logging configuration still works by running the relevant smoke tests.

### 2.3 OpenAI Client
- [x] Move the OpenAI client implementation from `computer_use_agent` to `shared/oai_client.py`.
- [x] Wire both agents to import the shared client and delete the old copies.
- [x] Confirm the client integrates with `TokenCostTracker` after the move.

## 3. Layer 1 – MCP Core Validation
- [x] Review `mcp_agent/mcp_client.py`, `registry.py`, and `oauth.py` to ensure no references to computer-use-specific code remain.
- [x] Add regression tests (or reuse existing ones) to confirm core registry refresh logic still runs when new Composio connections appear.

## 4. Layer 2 – Action Wrappers
- [x] Enumerate existing wrappers (`slack_post_message`, `gmail_send_email`, etc.) and confirm they only call MCP through `MCPAgent.current().call_tool`.
- [x] Normalize arguments inside each wrapper (lists vs strings, payload schemas) per plan requirements.
- [x] Ensure `emit_event(...)` telemetry fires from every wrapper call.
- [x] Document how new providers add wrappers without touching the planner.

## 5. Layer 3 – Toolbox & Manifest (Python Only)
- [x] Update `toolbox/builder.py` so `persist()` no longer references TypeScript generation.
- [x] Remove `toolbox/typescript.py` and any TS-specific manifests or stats.
- [x] Implement/plug in `PythonGenerator` that produces `sandbox_py/client.py`, `sandbox_py/__init__.py`, and `sandbox_py/servers/<provider>/<tool>.py`.
- [x] Ensure `search_tools(...)` remains the single discovery API by verifying no other module reads JSON manifests directly.
- [x] Persist generated Python sandbox files alongside JSON manifests and capture file stats for observability.

## 6. Layer 4 – Planner & Context Manager
- [x] Create `mcp_agent/planner/` package that owns prompts, context, budgets, and execution loop.
- [x] Centralize the new planner prompt (developer prompt acting as system) and store it in one module.
- [x] Implement deterministic context trimming that always retains planner prompt, task, and latest summaries once caps are hit.
- [x] Store tool summaries, sandbox summaries, discovery results, and budgets in a single context manager object.
- [x] Integrate `shared/oai_client` and `shared/token_cost_tracker` into the planner’s LLM call path.
- [x] Emit telemetry events (`mcp.search.run`, `mcp.action.called`, `mcp.sandbox.run`, `mcp.summary.created`, `mcp.budget.exceeded`) at the appropriate spots.

## 7. Layer 5 – Sandbox Runner
- [x] Implement `run_python_plan(code_body, user_id, toolbox_root, timeout_sec)` in a new module.
- [x] Ensure the runner writes a temporary `plan.py`, injects the generated sandbox imports, and executes it via a restricted subprocess.
- [x] Parse stdout/stderr to separate logs from the `___TB_RESULT___` JSON payload.
- [x] Return a `SandboxResult` object with `success`, `result`, `logs`, `error`, and `timed_out`.
- [x] Document the sandbox environment restrictions (no arbitrary network, limited PYTHONPATH) for future remote execution swaps.

## 8. Context, Prompt Governance & Summaries
- [x] Draft the canonical planner prompt covering mission, tool usage rules, sandbox guidelines, redaction rules, and context management.
- [x] Implement the sandbox prompt template example that demonstrates importing generated servers and emitting aggregate logs.
- [x] Build `summarize_payload(...)` per spec (label, original_size, truncated, schema, sample, aggregates, notes, storage_ref) with `purpose` tuning.
- [x] Add a redaction helper (or reuse one from `shared/logger`) that masks sensitive keys before logging or storing summaries.
- [x] Wire summarization to trigger automatically when payloads exceed size thresholds or are flagged as “wide”.

## 9. Discovery Workflow
- [x] Ensure the planner calls `search_tools(...)` on every new task and when registry versions change.
- [x] Store, deduplicate, and surface discovery results as a compact “tool menu” in context.
- [x] Support refined discovery queries (e.g., `search_tools("gmail attachments", detail_level="full")`) directly from planner decisions.
- [x] Confirm no provider-specific heuristics exist outside the discovery scoring path.

## 10. Sandbox Code Generation (Python Only)
- [x] Implement async wrappers in `sandbox_py/servers/...` that mirror `actions.py` signatures and call `sandbox_py.client.call_tool`.
- [x] Write docstrings/type hints in generated files using `ToolSpec` metadata.
- [x] Add `sandbox_py/client.py` utilities (`ToolCallResult`, `ToolCaller`, `register_tool_caller`, retries, payload sanitization, logging with redaction).
- [x] Provide integration glue so the planner (or tests) can register a tool caller that bridges to `MCPAgent` or a fake client.

## 11. Planner Loop & Budgets
- [x] Define the `Budget` dataclass (`max_steps`, `max_tool_calls`, `max_code_runs`, `max_llm_cost_usd`) and default values.
- [x] Track `steps_taken`, `tool_calls`, `code_runs`, and `estimated_llm_cost_usd` inside planner state.
- [x] After every LLM response, update the shared `TokenCostTracker` and compare cumulative cost against the budget.
- [x] Implement the planner loop logic: budget check → ensure discovery context → ask LLM → execute direct tool or sandbox → summarize → repeat/finish.
- [x] Return `MCPTaskResult` with `success=False` and a human-readable message when any budget is exceeded.

## 12. Summarization, Redaction & Telemetry Plumbing
- [x] Persist large tool/sandbox payloads to disk (`/workspace/tool-results/<task_id>/<label>.json`) when needed and store `storage_ref` in summaries.
- [x] Ensure redaction happens before writing logs or summaries to any storage.
- [x] Emit telemetry for summarization/redaction events so downstream systems can audit context hygiene.

## 13. Provider Inventory & Extensibility
- [x] Limit initial provider support to Composio-backed Gmail and Slack actions.
- [x] Verify the planner logic treats providers generically and only relies on `search_tools` metadata.
- [x] Document the onboarding steps for a new provider (add wrappers → ensure OAuth → regenerate toolbox).

## 14. Testing & Validation
- [x] Add unit tests for Python sandbox codegen (snapshot the generated files for at least one provider).
- [x] Test summarization/redaction helpers with large payload fixtures.
- [x] Write sandbox runner tests covering success, failure, and timeout scenarios.
- [x] Cover planner loop behavior for direct tool calls, sandbox runs, and budget exhaustion using fakes.
- [x] Add integration tests that simulate end-to-end Gmail/Slack tasks using stubbed MCP servers.

## 15. Migration & Cleanup
- [x] Remove any remaining TypeScript assets or references after Python-only generation ships.
- [x] Update documentation (README, flow_doc, etc.) to reflect the new architecture and CLI/library usage.
- [x] Ensure legacy automation scripts (if any) either call the new planner or are explicitly deprecated.
