# TakeBridge-S3

## Standalone MCP Planner

The repository now exposes a Python-only planner entrypoint at
`mcp_agent.agent.execute_mcp_task(task: str, *, user_id: str, budget: Budget | None = None, extra_context: dict | None = None) -> MCPTaskResult`.

- Returns a structured result with `success`, `final_summary`, `raw_outputs`, `budget_usage`, `logs`, and optional `error`.
- Budgets cover steps, tool calls, sandbox runs, and estimated LLM spend (tracked via `shared.token_cost_tracker`).
- Planner modules **must not** import from `computer_use_agent/`; this guarantees the standalone agent stays decoupled from the computer-use implementation.
- Initial provider coverage is limited to Composio-backed **Slack** and **Gmail** wrappers defined in `mcp_agent.actions`.
- Toolbox generation is now Python-only; TypeScript manifests have been removed to avoid stale dual stacks.

### Provider onboarding

To add another provider in this architecture:

1. Implement wrapper functions in `mcp_agent.actions` that normalize inputs and call `MCPAgent.current(user_id).call_tool`.
2. Ensure OAuth/registry configuration is available (via `OAuthManager`) so the builder can mark the provider as authorized and the wrappers can execute.
3. Regenerate the toolbox (`toolbox/builder.py`) so manifests and sandbox Python stubs include the new provider; the planner continues to consume discovery data via `search_tools(...)`.

### Sandbox + testing hooks

- Every call to `execute_mcp_task(...)` now builds an ephemeral `sandbox_py` package inside a temporary directory, so sandbox code always runs against a clean, per-request toolbox without touching the repo’s `toolbox/` tree.
- The sandbox runner automatically calls `mcp_agent.sandbox.glue.register_default_tool_caller()`, which wires generated wrappers to the active MCP registry. Set `TB_DISABLE_SANDBOX_CALLER=1` when you need to opt out and register your own caller.
- Tests (and local demos) can supply fake MCP clients by exporting `MCP_FAKE_CLIENT_FACTORY="tests.fakes.fake_mcp:build_fake_clients"`. The factory is invoked inside both the planner process and sandbox subprocesses, keeping tool calls offline and deterministic.

### Migration notes

- Action helpers in `mcp_agent/actions.py` now return structured `ToolInvocationResult` dictionaries (`successful`, `error`, `data`, etc.) instead of Python string snippets; update any direct consumers accordingly.
- Multi-tenant runs rely on a normalized `user_id` and the `TB_USER_ID` environment variable. The planner sets this automatically for sandbox subprocesses, but bespoke runners must export it before invoking generated sandbox code to ensure MCP calls route to the correct registry bucket.
- MCP registries, toolbox manifests, and planner raw outputs are now scoped per user and guarded by locks so concurrent requests do not leak state. When integrating, always pass the caller’s stable `user_id` into `execute_mcp_task(...)`. For local testing, use `mcp_agent.dev.resolve_dev_user()` or export `TB_USER_ID` once and reuse it.

### Legacy scripts

The orchestration helpers in `scripts/` remain for the FastAPI-based worker. Prefer calling `mcp_agent.agent.execute_mcp_task(...)` for all new automation. If you continue to use the scripts, treat them as legacy shims until they are fully re-wired to the standalone planner.

Refer to `Standalone_MCP_Plan.md` for the end-to-end architecture and the checklist for granular implementation status.

## Sandbox Runner

Sandbox plans run via `mcp_agent.execution.sandbox.run_python_plan(...)`, which wires up the temporary `sandbox_py` package created for the current request. The runner:

- Writes a temporary `plan.py` populated with the model-authored async function body.
- Sets `PYTHONPATH` to include the ephemeral toolbox first (so `from sandbox_py.servers import ...` succeeds) plus the repo root and original `PYTHONPATH` entries.
- Launches a subprocess using the same Python interpreter, with a configurable timeout (`timeout_sec`).
- Captures stdout/stderr, separates logs from the `___TB_RESULT___{json}` sentinel, and returns a structured `SandboxResult`.
- Emits no additional network access beyond the tool calls routed through the registered sandbox client; arbitrary outbound requests are unsupported in this MVP.
