Here’s a step-by-step implementation checklist in Markdown, directly mapped to the plan you pasted. You can literally paste this into a `PLAN.md` and tick things off as you go.

---
# MCP Planner & Toolbox Refactor – Implementation Checklist
---

## 1. Fix toolbox & search implementation

### 1.1. Normalize `ToolSpec` / `ProviderSpec` semantics

**File: `mcp_agent/toolbox/models.py`**

* [x] **Extend `ToolSpec` with convenience properties**

  * [ ] Add:

    ```python
    @property
    def tool_id(self) -> str:
        return f"{self.provider}.{self.name}"
    ```

  * [ ] Add:

    ```python
    @property
    def server(self) -> str:
        return self.provider
    ```

  * [ ] Add:

    ```python
    @property
    def py_module(self) -> str:
        return f"sandbox_py.servers.{self.provider}"
    ```

  * [ ] Add:

    ```python
    @property
    def py_name(self) -> str:
        return self.python_name
    ```

  * [ ] Add `params` property derived from `self.parameters`:

    ```python
    @property
    def params(self) -> dict:
        required = {}
        optional = {}
        for p in self.parameters:
            target = required if p.required else optional
            target[p.name] = p.annotation or "Any"
        return {"required": required, "optional": optional}
    ```

* [x] **Add `available_tools` to `ProviderSpec`**

  * [ ] Under `ProviderSpec.summary()` add:

    ```python
    @property
    def available_tools(self) -> list[str]:
        return [tool.name for tool in self.actions if tool.available]
    ```

  * [ ] Confirm that any existing references to `prov.available_tools` now work.

  * [ ] Prefer future logic to use `any(t.available for t in prov.actions)` where appropriate, but keep this property for compatibility and logging.

---

### 1.2. Build a global `ToolboxIndex`

**New file: `mcp_agent/toolbox/index.py`**

* [x] **Create `ToolboxIndex` dataclass**

  ```python
  from __future__ import annotations
  from dataclasses import dataclass
  from typing import Dict

  from .models import ToolboxManifest, ProviderSpec, ToolSpec

  @dataclass
  class ToolboxIndex:
      providers: Dict[str, ProviderSpec]
      tools_by_id: Dict[str, ToolSpec]

      @classmethod
      def from_manifest(cls, manifest: ToolboxManifest) -> "ToolboxIndex":
          providers_map = manifest.provider_map()
          tools_by_id: Dict[str, ToolSpec] = {}
          for provider in manifest.providers:
              for tool in provider.actions:
                  tools_by_id[tool.tool_id] = tool
          return cls(providers=providers_map, tools_by_id=tools_by_id)

      def get_tool(self, tool_id: str) -> ToolSpec | None:
          return self.tools_by_id.get(tool_id)
  ```

* [ ] **Expose a `get_index` helper**

**File: `mcp_agent/toolbox/builder.py` (or similar)**

  * [x] Import `ToolboxIndex` from `.index`.

  * [x] Implement:

    ```python
    from .index import ToolboxIndex

    def get_index(user_id: str, *, base_dir: Path | None = None) -> ToolboxIndex:
        manifest = get_manifest(user_id=user_id, base_dir=base_dir, persist=False)
        return ToolboxIndex.from_manifest(manifest)
    ```

  * [ ] If needed, consider caching `ToolboxIndex` similarly to `_MANIFEST_CACHE` (optional for first pass).

---

### 1.3. Fix `search_tools(...)` to use the index and never throw

**File: `mcp_agent/toolbox/search.py`**

* [x] **Replace fragile `available_tools` usage**

  * [x] Locate loop like:

    ```python
    for prov in manifest.providers:
        if not (prov.authorized and prov.registered and prov.available_tools):
            continue
    ```

  * [x] Replace with logic based on `ToolboxIndex`:

    ```python
    from .builder import get_index

    def search_tools(..., user_id: str) -> list[dict]:
        normalized_user = normalize_user_id(user_id)
        index = get_index(user_id=normalized_user, base_dir=None)
        norm_query = _normalize_query(query)
        provider_filter = provider.lower().strip() if provider else None

        matches: list[tuple[int, ProviderSpec, ToolSpec]] = []

        for prov in index.providers.values():
            if not (prov.authorized and prov.registered and any(t.available for t in prov.actions)):
                continue
            if provider_filter and prov.provider.lower() != provider_filter:
                continue
            for tool in prov.actions:
                if not tool.available:
                    continue
                score = _score_tool(tool, norm_query)
                if norm_query.terms and score == 0:
                    continue
                matches.append((score, prov, tool))

        # sort + limit
        matches.sort(key=lambda x: x[0], reverse=True)
        top = matches[:limit]

        formatter = _result_formatter(detail_level)
        return [formatter(score, prov, tool) for (score, prov, tool) in top]
    ```

* [x] **Ensure error handling doesn’t leak exceptions**

  * [x] Verify that wherever `search_tools` is called (likely in `mcp_agent/planner/discovery.py`), exceptions are caught and logged as `mcp.search.error`, then `[]` is returned.
  * [x] Confirm that no `ProviderSpec.available_tools` AttributeError can occur anymore.

* [x] **Keep backward-compatible keys in results**

  * [x] Ensure search results still carry `provider`, `tool`, `path`, `mcp_tool_name` as needed (will be done in the next step with `_format_for_planner`).

---

## 2. Standardize search result shape for the planner

### 2.1. Implement standardized search result formatter

**File: `mcp_agent/toolbox/search.py`**

* [x] **Add `_format_for_planner`**

  ```python
  def _format_for_planner(score: int, provider: ProviderSpec, tool: ToolSpec) -> dict:
      return {
          "tool_id": tool.tool_id,
          "server": tool.server,
          "py_module": tool.py_module,
          "py_name": tool.py_name,
          "description": tool.short_description or tool.description,
          "params": tool.params,
          "score": score,
          # compatibility fields:
          "provider": provider.provider,
          "tool": tool.name,
          "qualified_name": f"{provider.provider}.{tool.name}",
          "available": tool.available,
          "path": f"sandbox_py/servers/{provider.provider}/{tool.name}.py",
          "mcp_tool_name": tool.mcp_tool_name or tool.name.upper(),
      }
  ```

* [x] **Wire `_format_for_planner` into `search_tools`**

  * [x] In `_result_formatter(detail_level)`, ensure `detail_level == "summary"` returns `_format_for_planner`.

---

### 2.2. Update `PlannerContext` state & `available_servers`

**File: `mcp_agent/planner/context.py`**

* [x] **Verify search results are stored as full objects**

  * [ ] Ensure `PlannerContext.add_search_results(...)` / similar is storing the formatted dicts from `search_tools` in `self.search_results`.
  * [ ] Confirm that `planner_state()` includes `recent_steps` entries for type `"search"` with `"output"` equal to the array of these tool dicts.

* [x] **Recompute `available_servers` from search results instead of tool menu**

  * [ ] Find existing logic in `planner_state()` similar to:

    ```python
    available_servers = sorted(
        {entry["provider"] for entry in self.tool_menu if entry.get("provider")}
    )
    ```

  * [ ] Replace it with:

    ```python
    available_servers = sorted(
        {
            (entry.get("server") or entry.get("provider", "")).strip()
            for entry in self.search_results
            if (entry.get("server") or entry.get("provider"))
        }
    )
    ```

* [ ] **Keep tool menu for UI, but treat search results as source of truth**

  * [ ] Leave `tool_menu` derivation as-is or adapt later; the planners’ main “knowledge” about tools should come from `recent_steps` search outputs.

---

## 3. Planner protocol & parser updates

### 3.1. Support new action types (`search`, `tool`, `sandbox`, `fail`)

**File: `mcp_agent/planner/parser.py`**

* [x] **Allow `fail` type**

  * [x] Extend allowed types check to include `"fail"`:

    ```python
    if cmd_type not in {"tool", "sandbox", "finish", "search", "fail"}:
        raise ValueError("Planner response missing 'type' or unsupported command.")
    ```

* [x] **Enforce a `reasoning` string on all commands**

  * [x] In `parse_planner_command`, after parsing the JSON:

    ```python
    reasoning = command.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("Planner command must include non-empty 'reasoning' string.")
    command["reasoning"] = reasoning.strip()
    ```

  * [ ] (If you want a soft rollout, initially log instead of raising, but plan is to enforce.)

* [x] **Add `_validate_fail`**

  ```python
  def _validate_fail(command: dict) -> None:
      reason = command.get("reason")
      _ensure(
          isinstance(reason, str) and reason.strip(),
          "Fail command requires non-empty 'reason'.",
      )
  ```

  * [x] Register `_validate_fail` in the validators map.

* [x] **Extend `_validate_tool` to support new and legacy shapes**

  * [ ] Implement dual-path validation:

    ```python
    def _validate_tool(command: dict) -> None:
        tool_id = command.get("tool_id")
        server = command.get("server")
        args = command.get("args")

        provider = command.get("provider")
        tool = command.get("tool")
        payload = command.get("payload")

        if tool_id and server:
            _ensure(isinstance(tool_id, str) and tool_id.strip(), "Tool command requires non-empty 'tool_id'.")
            _ensure(isinstance(server, str) and server.strip(), "Tool command requires non-empty 'server'.")
            if args is None:
                args = {}
            _ensure(isinstance(args, dict), "Tool command 'args' must be an object.")
            command["tool_id"] = tool_id.strip()
            command["server"] = server.strip()
            command["args"] = args
        else:
            _ensure(isinstance(provider, str) and provider.strip(), "Tool command requires non-empty 'provider'.")
            _ensure(isinstance(tool, str) and tool.strip(), "Tool command requires non-empty 'tool'.")
            if payload is None:
                payload = {}
            _ensure(isinstance(payload, dict), "Tool command 'payload' must be an object.")
            command["provider"] = provider.strip()
            command["tool"] = tool.strip()
            command["payload"] = payload
    ```

---

### 3.2. Update planner system prompt

**File: `mcp_agent/planner/prompt.py`**

* [x] **Document allowed action types and schemas**

  * [ ] Add explicit JSON examples for:

    * `search` with `reasoning`
    * `tool` with `tool_id`, `server`, `args`, `reasoning`
    * `sandbox` with `label`, `code`, `reasoning`
    * `fail` with `reason`, `reasoning`

* [x] **Add search-first rule**

  * [x] Add text like:

    > Before using any server or tool, you MUST call a `"type": "search"` action at least once to look for it. You may only use tools whose specs appear in previous search results during this task.

* [x] **Ban invented tools/providers**

  * [x] Add:

    > You must not invent provider names, server modules, or function names. When you emit a `tool` or `sandbox` action, you must use the `server`, `py_module`, and `py_name` fields exactly as shown in the search results.

* [x] **Require `reasoning` key**

  * [x] Add:

    > Every action you emit MUST include a short `"reasoning"` string (1–3 sentences) explaining at a high level why this is the best next action. This reasoning is internal and not user-facing.

* [x] **Failure when discovery fails**

  * [x] Add:

    > If multiple searches fail to find suitable tools for the task, you MUST emit a final `"type": "fail"` action with a clear `"reason"` instead of guessing or fabricating tools.

* [x] **Keep “JSON only” behavior**

  * [x] Ensure the prompt still instructs: “Return only a single JSON object; do not include any other text.”

---

## 4. Runtime validation for `tool` and `sandbox` actions

### 4.1. Validate `tool` actions against index + search history

**File: `mcp_agent/planner/runtime.py` (or equivalent)**

* [x] **Normalize command shape**

  * [x] In `_execute_tool` (or equivalent):

    ```python
    tool_id = command.get("tool_id")
    server = command.get("server")
    args = command.get("args") or {}

    if not tool_id or not server:
        provider = command.get("provider")
        tool_name = command.get("tool")
        payload = command.get("payload") or {}
        tool_id = f"{provider}.{tool_name}"
        server = provider
        args = payload
    ```

* [x] **Look up tool in `ToolboxIndex`**

  * [x] Get index:

    ```python
    from mcp_agent.toolbox.builder import get_index
    index = get_index(self.context.user_id)
    spec = index.get_tool(tool_id)
    ```

  * [x] If `spec is None`:

    ```python
    return self._failure(
        "planner_used_unknown_tool",
        f"Planner requested unknown tool_id '{tool_id}'.",
        preview=str(command),
    )
    ```

* [x] **Ensure tool was discovered via search**

  * [x] Compute discovered ids:

    ```python
    discovered_tool_ids = {
        entry.get("tool_id")
        for entry in self.context.search_results
        if entry.get("tool_id")
    }
    ```

  * [x] If `tool_id` not in this set (and searches have run), treat as `planner_used_undiscovered_tool`.

* [x] **Map to MCP call and execute**

  * [x] Use `spec.provider` / `spec.name` to build the MCP call.
  * [x] Use `args` as the payload.
  * [x] Proceed with your existing `call_direct_tool` or equivalent.

* [x] **Record reasoning with the step**

  * [x] When calling `self.context.record_step(...)`, include the `reasoning` (used as preview when available).

---

### 4.2. Add sandbox AST validation

**New helper (or file): `mcp_agent/planner/sandbox_validator.py`**
**And integrated from `mcp_agent/planner/runtime.py`**

* [x] **Implement AST visitor**

  ```python
  import ast

  def analyze_sandbox(code: str) -> tuple[set[str], dict[str, set[str]]]:
      used_servers: set[str] = set()
      calls_by_server: dict[str, set[str]] = {}

      class SandboxVisitor(ast.NodeVisitor):
          def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
              if node.module == "sandbox_py.servers":
                  for alias in node.names:
                      used_servers.add(alias.name)
              self.generic_visit(node)

          def visit_Import(self, node: ast.Import) -> None:
              for alias in node.names:
                  if alias.name.startswith("sandbox_py.servers."):
                      server = alias.name.split(".")[-1]
                      used_servers.add(server)
              self.generic_visit(node)

          def visit_Call(self, node: ast.Call) -> None:
              if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                  server = node.func.value.id
                  func_name = node.func.attr
                  calls_by_server.setdefault(server, set()).add(func_name)
              self.generic_visit(node)

      tree = ast.parse(code)
      SandboxVisitor().visit(tree)
      return used_servers, calls_by_server
  ```

* [x] **Integrate validator into sandbox execution**

  **In `_execute_sandbox` (or equivalent):**

  * [x] Parse & catch syntax error:

    ```python
    try:
        used_servers, calls_by_server = analyze_sandbox(code_body)
    except SyntaxError as exc:
        return self._failure(
            "sandbox_syntax_error",
            f"Sandbox code has invalid syntax: {exc}",
            preview=str(command),
        )
    ```

  * [x] Build allowed servers from search results:

    ```python
    allowed_servers = {
        (entry.get("server") or entry.get("provider"))
        for entry in self.context.search_results
        if entry.get("server") or entry.get("provider")
    }
    ```

  * [x] Build `allowed_py_names_by_server`:

    ```python
    allowed_py_names_by_server: dict[str, set[str]] = {}
    for entry in self.context.search_results:
        server = (entry.get("server") or entry.get("provider"))
        py_name = entry.get("py_name") or entry.get("tool")
        if server and py_name:
            allowed_py_names_by_server.setdefault(server, set()).add(py_name)
    ```

  * [x] **Reject unknown servers:**

    ```python
    for server in used_servers:
        if server not in allowed_servers:
            return self._failure(
                "planner_used_unknown_server",
                f"Sandbox used server '{server}' which was never discovered via search.",
                preview=str(command),
            )
    ```

  * [x] **Reject undiscovered functions:**

    ```python
    for server, funcs in calls_by_server.items():
        allowed_funcs = allowed_py_names_by_server.get(server, set())
        for func in funcs:
            if func not in allowed_funcs:
                return self._failure(
                    "planner_used_undiscovered_tool",
                    f"Sandbox used '{server}.{func}' which was not in search results.",
                    preview=str(command),
                )
    ```

  * [x] Only after passing these checks, call the sandbox runner.

---

## 5. Failure behavior when discovery fails

### 5.1. Prompt-level rule

**File: `mcp_agent/planner/prompt.py`**

* [x] **Add rule about repeated empty searches**

  * [x] Add text like:

    > If 2–3 searches (with different but related queries) fail to find any matching tools for the required capability (for example, Gmail inbox), you MUST emit a final `{"type": "fail", ...}` action. Do not attempt to guess or fabricate tools.

---

### 5.2. Runtime-level safety net

**File: `mcp_agent/planner/runtime.py`**

* [x] **Track search attempts and results in context**

  * [x] Ensure you can count how many search steps have occurred and whether they had non-empty `output`.

* [x] **On validation errors + prior empty searches, map to `discovery_failed`**

  * [x] In cases where:

    * Error is `planner_used_unknown_tool`, `planner_used_unknown_server`, or `planner_used_undiscovered_tool`, **and**
    * There have already been ≥ N search steps with only empty results,

    convert to a clean failure, e.g.:

    ```python
    return self._failure(
        "discovery_failed",
        "No suitable tools were found via search, so this environment cannot complete the requested task.",
        preview=str(command),
    )
    ```

* [x] **Ensure final `MCPTaskResult` surfaces this clearly** (e.g., `final_summary` uses this message).

---

## 6. Logging & Tests

### 6.1. Logging

**File: `mcp_agent/planner/context.py` & runtime**

* [x] **Add `mcp.search.completed`**

  * [x] Log: `query`, `detail_level`, `result_count`, `tool_ids`.

* [x] **Add `mcp.planner.protocol_error`**

  * [x] Trigger in `parse_planner_command` when JSON/schema is invalid.
  * [x] Include raw preview of model output.

* [x] **Add `mcp.planner.validation_error`**

  * [x] Use for:

    * `planner_used_unknown_tool`
    * `planner_used_undiscovered_tool`
    * `planner_used_unknown_server`
    * `sandbox_syntax_error`

* [x] **Extend `mcp.planner.failed` reasons**

  * [x] Include new reasons:

    * `discovery_failed`
    * `planner_used_unknown_tool`
    * `planner_used_undiscovered_tool`
    * `planner_used_unknown_server`
    * `sandbox_runtime_error`

---

### 6.2. Tests

* [x] **Search tests**

  * [x] With a manifest that includes Gmail/Slack:

    * [x] `search_tools("slack", ...)` returns entries with correct `tool_id`, `server`, `py_module`, `py_name`.
  * [x] Verify no `AttributeError` regarding `available_tools`.

* [x] **Protocol tests**

  * [x] `parse_planner_command` rejects missing/empty `"reasoning"`.
  * [x] `parse_planner_command` accepts both:

    * New `{"tool_id", "server", "args"}`
    * Legacy `{"provider", "tool", "payload"}` (via validation logic).

* [x] **Sandbox validator tests**

  * [x] Sandbox using `from sandbox_py.servers import gmail` and no discovery fails with `planner_used_unknown_server`.

* [x] **Tool validation tests**

  * [x] `tool` command with unknown `tool_id` fails with `planner_used_unknown_tool`.
  * [x] `tool` command with correct `tool_id` but never discovered fails with `planner_used_undiscovered_tool`.

* [x] **Failure behavior test**

  * [x] Simulate:

    * Multiple search steps returning `[]`.
    * Planner emitting a sandbox referencing “gmail”.
  * [x] Assert final result:

    * `success == False`
    * `error == "discovery_failed"`
    * `final_summary` explains missing tools.

---

## 7. Reasoning summary on every step

**Files: `mcp_agent/planner/llm.py`, `mcp_agent/planner/parser.py`, `mcp_agent/planner/runtime.py`, `prompt.py`**

* [ ] **Confirm Responses API reasoning config**

  * [ ] In `PlannerLLM.generate_plan`, ensure:

    ```python
    json_mode_kwargs = {
        "model": self.model,
        "messages": messages,
        "reasoning_effort": "high",
        "max_output_tokens": 10000,
        "text": json_mode_text,
        "reasoning_summary": "auto",  # or "concise"
    }
    ```

* [x] **Prompt explicitly requires `"reasoning"` key** (done in §3.2).

* [x] **Parser enforces `reasoning` presence** (done in §3.1).

* [x] **Runtime logs reasoning per step**

  * [x] Ensure calls to `record_step()` include the `reasoning` string so logs show high-level planner thinking without full CoT.

---
