# MCP Agent

Provider-agnostic MCP tooling that powers both the standalone planner and the computer-use agent.

## Adding A New Provider
Follow these steps to introduce a new provider without touching planner logic:

1. **Create wrappers in `mcp_agent/actions.py`:**
   - Decorate each wrapper with `@mcp_action`.
   - Normalize parameters inside the wrapper (strings vs lists, structured payloads).
   - Call `MCPAgent.current().call_tool(provider, TOOL_NAME, payload)` via the helper `_invoke_mcp_tool`.
   - Emit telemetry by relying on `_emit_action_event`; unauthorized paths should emit `mcp.call.skipped`.

2. **Register the wrapper:**
   - Add the new functions to `_provider_actions_map()` so discovery/build steps can find them.
   - Ensure any provider-specific OAuth configuration exists in `mcp_agent.oauth.OAuthManager`.

3. **Refresh toolbox artifacts:**
   - Run the Python-only toolbox builder (future `ToolboxBuilder.refresh_manifest`) so `toolbox/manifest.json` and generated sandbox stubs include the new provider.

4. **Write/extend tests:**
   - Add unit tests covering normalization rules and telemetry expectations (see `tests/mcp_core/test_actions.py` for examples).

With these steps complete, planners only need to call `search_tools(...)`; no planner changes are required for new providers.
