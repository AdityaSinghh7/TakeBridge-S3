# Adding MCP Tools and Providers

This document describes the canonical contracts and the step‑by‑step process for
adding new MCP providers and tools to the TakeBridge planner/toolbox.

The goals are:

- One **canonical response wrapper** for all MCP tool calls.
- Clear, human‑readable **input parameter docs** for each tool.
- A repeatable process for documenting the **`data` schema** of tool responses.

The current implementations for Slack and Gmail are the reference examples.

---

## 1. Canonical ActionResponse contract

All Composio/MCP tool wrappers normalize their output into a shared wrapper.

Defined in `mcp_agent/toolbox/types.py:ActionResponse`:

```python
class ActionResponse(TypedDict, total=False):
    successful: bool
    data: dict[str, Any]
    error: Optional[str]
    raw: Any | None
```

Notes:

- `successful` is the canonical success flag inside the planner/toolbox.
- `data` is always a dict in normalized responses (possibly empty).
- `error` is a human‑readable error message (or `None` when successful).
- `raw` carries the original provider payload for debugging/inspection.
- Internally we may attach additional fields (e.g. `logs`, `provider`, `tool`),
  but callers can always rely on the fields above.

Wrappers in `mcp_agent/actions.py` already follow this contract via
`ToolInvocationResult`, which is a superset of `ActionResponse`. New wrappers
should continue to normalize into this shape.

---

## 2. Manual input schema (parameters)

Input schemas are defined through:

- The Python signature of each wrapper (types and defaults).
- A structured docstring with `Description:` and `Args:` sections.

Toolbox metadata is derived from these via `ToolboxBuilder`:

- `mcp_agent/toolbox/builder.py` inspects wrappers in `mcp_agent/actions.py`.
- It builds a `ToolSpec` (`mcp_agent/toolbox/models.py`) containing:
  - `provider`, `name` (tool name), `python_name`, `python_signature`
  - `parameters` (a list of `ParameterSpec` with name, type, required, default)
  - `short_description` and full `description` from the docstring

The LLM‑facing descriptor (`LLMToolDescriptor`) is produced by
`ToolSpec.to_llm_descriptor(...)` and surfaced via `search_tools(...)`. It
includes:

- `call_signature` – Python‑style signature ready to copy into sandbox code.
- `input_params_pretty` – lines of human‑readable parameter documentation.
- `input_params` – machine‑readable description of required and optional params.

For the currently implemented tools (Slack and Gmail), the signatures and
docstrings in `mcp_agent/actions.py` are the source of truth for input schemas.

When adding a new tool, you must:

- Use accurate type annotations in the function signature.
- Keep docstrings up to date under `Description:` and `Args:`.

`ToolboxBuilder` will pick these up automatically.

---

## 3. Output schema for `ActionResponse.data`

Every tool response uses the envelope:

```python
{
    "successful": bool,
    "data": dict,         # tool‑specific payload
    "error": str | None,
    ...
}
```

The planner and sandbox only need to know the structure of `data`. We attach
this information to wrappers using the `tool_output_schema` decorator.

Defined in `mcp_agent/tool_schemas.py`:

```python
def tool_output_schema(schema: Dict[str, Any], pretty: Optional[str] = None):
    \"\"\"Attach a description of the tool's `data` field schema to a wrapper.\"\"\"
```

Usage in `mcp_agent/actions.py` (examples):

- `slack_post_message`
- `slack_search_messages`
- `gmail_send_email`
- `gmail_search`

The decorator attaches:

- `__tb_output_schema__`: machine‑readable structure for `data`.
- `__tb_output_schema_pretty__`: human‑readable lines describing `data`.

`ToolboxBuilder._build_tool(...)` stores these on `ToolSpec` as
`output_schema` and `output_schema_pretty`. Later:

- `ToolSpec.to_llm_descriptor(...)` feeds `output_schema_pretty` into
  `LLMToolDescriptor.output_schema_pretty`, which the planner exposes to the
  LLM as the authoritative description of what lives under the `data` key.

Runtime discovery uses wrapper-provided output schemas only; we do not load
generated schema files for tool discovery.

Placeholder schemas are acceptable for now as long as the text explicitly notes
that they must be replaced with real Composio‑compatible schemas in a follow‑up
pass.

---

## 4. Planner‑facing tool descriptor (search_tools)

The only discovery API for the planner is:

- `mcp_agent/toolbox/search.py:search_tools(...)`

It returns a list of tool descriptors (one per available tool) with the
following planner‑relevant fields:

- `provider` – provider id (e.g. `"gmail"`).
- `server` – logical server/module alias (usually same as provider).
- `module` – sandbox module path (e.g. `"sandbox_py.servers.gmail"`).
- `function` – sandbox helper function (e.g. `"gmail_search"`).
- `tool_id` – stable id (e.g. `"gmail.gmail_search"`).
- `call_signature` – copy‑pasteable signature for sandbox code.
- `description` – short tool description.
- `input_params_pretty` – human‑readable parameter docs.
- `output_schema_pretty` – human‑readable description of `data` under the
  canonical wrapper.
- `input_params` – machine‑readable required/optional param metadata.
- `output_schema` – machine‑readable `data` schema.
- `score` – numeric relevance for ranking.

Legacy/compatibility fields (e.g. `py_module`, `py_name`, `path`) are included
for existing planner code and UI, but internal fields such as `mcp_tool_name`,
OAuth flags, or source paths are **not** exposed to the LLM.

---

## 5. Checklist: adding a new tool for an existing provider

Example: add `gmail_archive_thread`.

1. **Add or update the wrapper**

   - File: `mcp_agent/actions.py` (or a future provider‑specific module).
   - Implement the wrapper using the `mcp_action` decorator and normalize any
     raw MCP response into `ActionResponse`/`ToolInvocationResult`:

   ```python
   @mcp_action
   def gmail_archive_thread(self, thread_id: str) -> ToolInvocationResult:
       \"\"\"
       Description:
           Archives a Gmail thread by id.
       Args:
           thread_id: Gmail thread id to archive.
       \"\"\"
       tool_name = "GMAIL_ARCHIVE_THREAD"
       user_id = _current_user_id()
       if getattr(self, "_validation_only", False):
           return _structured_result(
               "gmail",
               tool_name,
               successful=True,
               data={"skipped": "validation_only"},
               payload_keys=[],
           )
       if not OAuthManager.is_authorized("gmail", user_id=user_id):
           emit_event(
               "mcp.call.skipped",
               {"server": "gmail", "tool": tool_name, "reason": "unauthorized", "user_id": user_id},
           )
           return _structured_result(
               "gmail",
               tool_name,
               successful=False,
               error="unauthorized",
               payload_keys=[],
           )

       payload = {"thread_id": thread_id}
       return _invoke_mcp_tool("gmail", tool_name, payload)
   ```

   Requirements:

   - Accurate type annotations in the signature.
   - Up‑to‑date `Description:` and `Args:` sections in the docstring.
   - Use `_structured_result` / `_normalize_tool_response` so the result
     conforms to the ActionResponse contract.

2. **Describe the output schema**

   - Add a `tool_output_schema` decorator above the wrapper:

   ```python
   from mcp_agent.tool_schemas import tool_output_schema


   @tool_output_schema(
       schema={
           "data": {
               "threadId": "str",
               "archived": "bool",
           }
       },
       pretty=\"\"\"
   Canonical wrapper: { successful: bool, data: dict, error: str | null }

   data: {
     threadId: str,
     archived: bool,
   }

   Note: This schema is a placeholder; align it with the Composio GMAIL_ARCHIVE_THREAD
   response once the connector contract is finalized.
   \"\"\".strip(),
   )
   @mcp_action
   def gmail_archive_thread(...):
       ...
   ```

   - If you do not yet know the exact `data` payload, write a clearly‑marked
     placeholder and follow up later.

3. **Regenerate toolbox metadata and sandbox helpers**

   - Run a short script or use an existing admin endpoint that invokes:

   ```python
   from mcp_agent.toolbox.builder import ToolboxBuilder

   builder = ToolboxBuilder(user_id="<test-user>")
   manifest = builder.build()
   builder.persist(manifest)
   ```

   This will:

   - Update `toolbox/manifest.json` for the user.
   - Persist provider/tool JSON metadata.
   - Regenerate `sandbox_py` helpers for sandbox code.

4. **Verify the tool is discoverable**

   - Use `search_tools(...)` directly in a REPL, or call the HTTP endpoint:
     `GET /api/mcp/auth/tools/search?q=gmail archive&detail=summary`.
   - Confirm the result entry contains:
     - `provider`, `server`, `module`, `function`, `tool_id`
     - `call_signature`
     - `input_params_pretty`
     - `output_schema_pretty`

5. **Add tests where appropriate**

   - Unit‑test the wrapper behavior with fake or stubbed MCP clients:
     - Unauthorized path returns `successful=False`, `error="unauthorized"`.
     - Happy path calls the expected Composio tool name with the right payload.
   - Optionally assert on `search_tools(...)` output in the toolbox tests to
     ensure the descriptor shape is stable.

---

## 6. Checklist: adding a new provider

Example: add `notion`.

1. **Wire the provider into the core registry**

   - Update `mcp_agent/actions.py` (or a future provider‑specific module) to
     include wrappers for each MCP action you expose.
   - Add the provider and its actions to `SUPPORTED_PROVIDERS` and
     `PROVIDER_ACTIONS`.

2. **Ensure OAuth / MCP client support**

   - `mcp_agent/oauth.py` and `mcp_agent/registry.py` must know how to create an
     MCP client for the new provider (URL + headers).
   - Confirm that `init_registry(user_id)` registers the provider when
     configured.

3. **Implement wrappers and output schemas**

   - For each action:
     - Implement a wrapper with `mcp_action`.
     - Normalize the response to the ActionResponse/ToolInvocationResult shape.
     - Attach `tool_output_schema(...)` describing the `data` payload.

4. **Regenerate toolbox metadata**

   - Use `ToolboxBuilder` for a test user to regenerate the manifest and
     sandbox helpers.
   - Inspect `toolbox/providers/<provider>/tools/*.json` to verify the new
     tools are present and include expected metadata.

5. **Verify planner integration**

   - Use `search_tools(...)` to confirm the new tools surface correctly and
     include the descriptor fields described above.
   - Optionally add planner tests that:
     - Stub `search_tools` to return the new tool.
     - Exercise a simple planner run that calls the tool or uses the sandbox
       helper.

---

## 7. Summary

- **ActionResponse** is the canonical output wrapper: every MCP tool wrapper
  must behave like `{"successful": bool, "data": dict, "error": str | None}`.
- **Manual input schemas** come from accurate function signatures and
  docstrings in `mcp_agent/actions.py`; the toolbox derives `ToolSpec` and
  `LLMToolDescriptor` from these.
- **Output schemas** for `data` live on `ToolSpec.output_schema` and
  `ToolSpec.output_schema_pretty`, populated via `tool_output_schema` and
  consumed by the planner through `search_tools(...)`.

Following the checklists above keeps new tools/providers predictable for both
the planner and the sandbox, and avoids leaking internal implementation details
to the LLM.
