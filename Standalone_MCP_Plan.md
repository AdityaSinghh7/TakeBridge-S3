Standalone MCP Agent Plan (Detailed, Python-Only)

---

### 1. Goals & Scope

* Deliver a **fully Python** Standalone MCP Agent that:

  * Accepts a single **task string**.
  * Autonomously discovers tools, plans multi-step workflows.
  * Executes MCP tools and sandboxed Python code.
  * Returns a **structured result**.
* Operate **independently of `computer_use_agent/`** (no imports from it).
* Keep provider/tool logic **agnostic**, so new integrations only require:

  * Updating `mcp_agent.actions` and
  * Regenerating toolbox artifacts.
* Enforce strict **context hygiene**:

  * Centralized **planner prompt** (developer prompt used as system-level prompt).
  * Structured tool summaries.
  * Automatic redaction.
  * LLM cost tracking with budget enforcement (shared `TokenCostTracker`).

---

### 2. Layered Architecture

**Layer 0 – Shared Infrastructure**

* **`shared/` package** hosts cross-cutting utilities used by *both* agents:

  * `shared/token_cost_tracker.py` (moved from `computer_use_agent/utils/token_cost_tracker.py`).
  * `shared/logger.py` (moved from whatever logger module currently lives under `computer_use_agent/`).
  * `shared/oai_client.py` (moved from `computer_use_agent` into `shared/`), as the single OpenAI client used by:

    * Standalone MCP Agent, and
    * Computer-use agent.
* All LLM invocations and logging go through these shared modules.

**Layer 1 – MCP Core**

* Existing `mcp_agent` core remains:

  * `mcp_client.py` (HTTP MCP client).
  * `registry.py` (per-user MCP client registry; provider-neutral).
  * `oauth.py` (Composio white-label OAuth, DB-backed connections).
* Registry refreshes when new Composio connections appear; stays provider-agnostic.

**Layer 2 – Action Wrappers**

* `mcp_agent.actions` defines **provider-agnostic** wrappers:

  * `slack_post_message`, `slack_search_messages`, `gmail_send_email`, `gmail_search`, etc.
* **All new tools** are added here; planner is not modified for new providers.
* Wrappers:

  * Normalize arguments (string lists, structured payloads).
  * Call MCP via `MCPAgent.current().call_tool(...)`.
  * Emit `emit_event(...)` telemetry.

**Layer 3 – Toolbox & Manifest**

* `toolbox/` is responsible for:

  * Inspecting action wrappers (`get_provider_action_map()`).
  * Building a `ToolboxManifest` (providers, tools, metadata, availability).
  * Persisting:

    * `manifest.json`, `providers.json`, `providers/<provider>/provider.json`,
    * `providers/<provider>/tools/*.json`.
  * **Generating Python sandbox modules only** (TypeScript output removed).
* `search_tools(...)` remains the **sole discovery API** used by the planner.

**Layer 4 – Planner & Context**

* New `mcp_agent.planner` module:

  * Owns prompts, conversation state, budgets, summarization, sandbox orchestration.
  * Uses the shared `shared/oai_client.py` and `shared/token_cost_tracker.py`.
  * Exposes **single entry point**:

    ```python
    execute_mcp_task(
        task: str,
        user_id: str = "singleton",
        budget: Budget | None = None,
        extra_context: dict | None = None,
    ) -> MCPTaskResult
    ```

* `MCPTaskResult` is a structured object (or TypedDict) containing:

  * `success: bool`
  * `final_summary: str`
  * `raw_outputs: dict` (optional structured data)
  * `budget_usage: BudgetSnapshot`
  * `logs: list[dict]` (optional telemetry-friendly events)
  * `error: str | None`

**Layer 5 – Sandbox Runner**

* Python-only sandbox generated under `toolbox/sandbox_py`:

  * `sandbox_py/client.py` – Python tool caller client.
  * `sandbox_py/servers/<provider>/<tool>.py` – per-tool wrappers.
* `run_python_plan(...)`:

  * Spawns local Python subprocesses that import generated sandbox modules.
  * Executes agent-authored Python code in a **restricted environment**.
  * Returns structured `SandboxResult`.

---

### 3. Context & Prompt Governance

We **deprecate a separate “system prompt”** and standardize on a single **planner prompt**:

* **Developer prompt is the new system prompt.**

  * There is *one* canonical “planner prompt” used to steer the LLM.
  * It is injected as the top-level developer/system-like instruction for every task.
* The context manager maintains:

  * `planner_prompt` (canonical instructions).
  * `task` (user-provided string).
  * `search_results` (from `search_tools`).
  * `tool_summaries` (summarized outputs from tool calls).
  * `sandbox_summaries` (from sandbox runs).
  * `budgets` and `budget_usage`.
  * `llm_cost_state` (using shared `TokenCostTracker`).
* Governance rules:

  * **Deterministic trimming**:

    * Keep `planner_prompt`, `task`, and the most recent summaries.
    * Trim oldest conversation elements once total serialized context exceeds a configured cap (e.g., N characters or tokens).
  * **Planner prompt content**:

    * Mission and behavior (understand task, plan, execute tools/sandbox, summarize).
    * Tool usage rules (always search first, how to interpret search results).
    * **When to prefer direct tool calls vs sandbox code**:

      * Direct: single tool call or very simple sequence without complex logic.
      * Sandbox: loops, branching, data aggregation/filtering, or multiple tool calls with stateful logic.
    * Security rules (redaction, no raw huge dumps, etc.).
    * Context management rules (summaries not raw outputs).
  * **Sandbox prompt template**:

    * Shows correct usage pattern, for example:

      ```python
      from sandbox_py.servers import gmail, slack

      async def main():
          # use await gmail.gmailSendEmail(...)
          # log only aggregates or samples, not full datasets
          ...
      ```

    * Emphasizes: **log aggregates**, sample rows, or counts – not entire data blobs.

---

### 4. Discovery Workflow

* On every new task (and when lacking relevant info), planner calls:

  ```python
  search_tools(
      query=task,
      detail_level="summary",
      limit=40,
      user_id=user_id,
  )
  ```

* Results (for each provider/tool):

  * `provider`, `tool`, `short_description`, `parameters`, `available`, `path`, `mcp_tool_name`, etc.

* These are:

  * Stored in context,
  * Deduplicated by `(provider, tool)`,
  * Used to build a compact “tool menu” for the LLM.

* Planner helpers can issue **refined searches**, e.g.:

  ```python
  search_tools("gmail attachments", detail_level="full", limit=20, user_id=user_id)
  ```

* **No provider-specific heuristics** baked in:

  * All selection and prioritization flows through `search_tools` scoring.
  * This makes the planner robust as new providers/tools are added.

---

### 5. Summarization & Redaction

**Summarization pipeline**

* Implement:

  ```python
  summarize_payload(
      label: str,
      payload: Any,
      *,
      purpose: Literal["for_planning", "for_user", "for_debug"],
      max_chars: int = 4000,
  ) -> dict
  ```

* Trigger summarization when:

  * Serialized payload size > 16–32 KB, or
  * Data is obviously “wide” (large tables, long email threads, etc.).

* Output is **JSON-only**, with keys:

  * `label`: human-readable tag (e.g., "gmail_search_results").
  * `original_size`: size metadata (bytes, rows, count).
  * `truncated`: boolean.
  * `schema`: inferred structure (columns/fields).
  * `sample`: small sample of rows/items.
  * `aggregates`: derived stats (counts, sums, min/max, etc.).
  * `notes`: anomalies, important highlights, or warnings.
  * `storage_ref`: optional file path (e.g., `/workspace/tool-results/<task_id>/<label>.json`) where full payload is persisted.

* `purpose` tuning:

  * `for_planning`: emphasize schema + aggregates; terse notes.
  * `for_user`: slightly richer narrative but still compact.
  * `for_debug`: extra metadata, but still runs **redaction** first.

**Redaction**

* Add shared helper:

  ```python
  from shared.logger import redact_payload  # or shared.redaction

  redact_payload(
      payload: dict,
      sensitive_keys: list[str] = ["token", "authorization", "password", "api_key", "secret"],
  ) -> dict
  ```

* Redaction is applied:

  * Before writing logs to disk.
  * Before embedding content into prompt context.
  * Optionally before persisting tool results to files (depending on sensitivity).

* Sandbox coding rules (reinforced via planner prompt):

  * Don’t print full documents, raw email bodies in bulk, or entire tables.
  * Prefer aggregates (counts, totals), column lists, and a **tiny sample** of rows.

---

### 6. Sandbox & Toolbox Generation (Python-Only)

**Python codegen replaces TypeScript entirely**

* Introduce `PythonGenerator` (e.g., `toolbox/python_codegen.py`) that:

  * Generates `sandbox_py/client.py`.
  * Generates `sandbox_py/__init__.py`.
  * Generates `sandbox_py/servers/<provider>/<tool>.py` for each tool.
* Tool wrappers:

  * Expose async functions mirroring `actions.py` signatures.

  * Call:

    ```python
    from sandbox_py.client import call_tool

    await call_tool(provider="gmail", tool="GMAIL_SEND_EMAIL", payload=payload)
    ```

  * Include docstrings and type hints based on `ToolSpec`.

**ToolboxBuilder changes**

* `ToolboxBuilder.persist()`:

  * Continues to write all JSON manifests (`manifest.json`, `providers.json`, etc.).
  * Drops all TypeScript generation.
  * Calls `PythonGenerator.write()` and records `py_files` stats.
* `sandbox_py/client.py`:

  * Mirrors TS client behavior in Python:

    * `ToolCallResult` TypedDict.
    * `ToolCaller` protocol/callable.
    * `register_tool_caller(caller: ToolCaller)` to bind to actual MCP calls.
    * `call_tool()` with retries, minimal throttling, payload sanitization, and redaction for logs.

**Sandbox runner**

* Implement:

  ```python
  run_python_plan(
      code_body: str,
      *,
      user_id: str,
      toolbox_root: Path,
      timeout_sec: int = 30,
  ) -> SandboxResult
  ```

* Behavior:

  * Creates a temp working dir for the task.

  * Writes `plan.py` with template:

    ```python
    import asyncio
    from sandbox_py.servers import gmail, slack  # etc.

    async def main():
        # BEGIN MODEL-GENERATED CODE
        {{ code_body }}
        # END MODEL-GENERATED CODE

    if __name__ == "__main__":
        import json
        result = asyncio.run(main())
        print("___TB_RESULT___" + json.dumps(result or {}))
    ```

  * Sets `PYTHONPATH` to include `toolbox_root` and required libs.

  * Sets a **restricted environment** (no arbitrary network access; I/O limited as needed).

  * Executes `python plan.py` with timeout.

  * Parses stdout:

    * Everything before `___TB_RESULT___` → logs.
    * JSON after `___TB_RESULT___` → structured `result`.

  * Captures stderr into logs as well.

* `SandboxResult` includes:

  * `success: bool`
  * `result: dict | None`
  * `logs: list[str]`
  * `error: str | None`
  * `timed_out: bool`

* Future remote/worker execution:

  * Re-implement `run_python_plan()` to call a worker/HTTP service or microVM.
  * Planner remains unchanged.

---

### 7. Planner Loop & Budgets

**Budget model**

* `Budget` dataclass, e.g.:

  ```python
  @dataclass
  class Budget:
      max_steps: int = 10
      max_tool_calls: int = 30
      max_code_runs: int = 3
      max_llm_cost_usd: float = 0.50
  ```

* Defaults can be overridden per call to `execute_mcp_task()`.

**State tracking**

* Keep:

  * `steps_taken`
  * `tool_calls`
  * `code_runs`
  * `estimated_llm_cost_usd`
* After **every LLM call**:

  * Use `shared.token_cost_tracker.TokenCostTracker` to update cost for model `o4-mini`.
  * If `estimated_llm_cost_usd > budget.max_llm_cost_usd`, halt and return failure.

**Step flow (per planner iteration)**

1. **Check budgets**

   * If `steps_taken >= max_steps` or any other limit exceeded → return `MCPTaskResult` with `success=False`, `error="budget exceeded: ..."` and a partial summary.

2. **Ensure discovery context**

   * If tools have not been searched for this task, or registry version changed, call `search_tools(...)` and update context.

3. **Ask LLM (planner prompt)**

   * Provide:

     * `planner_prompt`.
     * Task string.
     * Top N tools (`provider`, `tool`, `description`, `parameters`, `availability`).
     * Latest summarized outputs (tool and sandbox).
     * Current budget snapshot.
   * Ask model to choose:

     * (a) Direct tool invocation, or
     * (b) Sandbox code plan, or
     * (c) Finalize.

4. **Direct action path**

   * LLM returns chosen `provider`, `tool`, and arguments.
   * Planner:

     * Validates tool availability.
     * Calls corresponding Python wrapper in `mcp_agent.actions`.
     * `tool_calls += 1`.
     * Summarizes result via `summarize_payload` (if large) and stores in context.
     * Logs event (`mcp.action.called`, `provider`, `tool`, `request`, `summary_ref`).

5. **Code mode path**

   * LLM returns a `code_body` (only body of `async def main()`).
   * Planner:

     * `code_runs += 1`.
     * Calls `run_python_plan(...)`.
     * Summarizes `SandboxResult` (logs + result) into context, possibly with `summarize_payload`.
     * Logs event (`mcp.sandbox.run`, success/failure, summary).

6. **Completion decision**

   * LLM either:

     * Marks task as complete and provides final summary.
     * Or requests another step.
   * Planner repeats until:

     * Task complete, or
     * Budget exceeded, or
     * Max steps reached.

**Telemetry**

* For each step and important event:

  * Emit structured events via `shared.logger` / `emit_event`:

    * `mcp.search.run`, `mcp.action.called`, `mcp.sandbox.run`, `mcp.summary.created`, `mcp.budget.exceeded`.
  * Events include `task_id`, `user_id`, `step_index`, and a minimal redacted payload.

---

### 8. Tool Inventory & Providers

* **Initial scope:**

  * Composio-backed **Gmail** and **Slack** only.
* Architecture is explicitly **provider-agnostic**:

  * No special-casing of Gmail/Slack in planner.
  * `search_tools` is the single discovery and ranking mechanism.
* To add a new provider:

  1. Implement wrappers in `mcp_agent.actions`.
  2. Ensure Composio/OAuth configuration exists.
  3. Run `ToolboxBuilder.refresh_manifest(...)` to regenerate manifest and Python sandbox wrappers.

---

### 9. Sandbox Environment Decisions

* MVP strategy:

  * Sandbox runs as **local Python subprocess** via `run_python_plan()`.
  * `PYTHONPATH` restricted to:

    * `sandbox_py`,
    * minimal allowed libraries.
  * Environment stripped down (no arbitrary network access, limited OS interaction).
* MCP calls from sandbox:

  * Go through `sandbox_py.client.register_tool_caller(...)` which bridges to:

    * `MCPAgent.current().call_tool` or directly to `MCPClient`.
* Future strategy:

  * Replace subprocess backend with:

    * Worker processes, containerized sandboxes, or microVMs (Firecracker-like).
  * Keep the **interface of `run_python_plan()` stable**, so the planner and toolbox do not change.

---

### 10. LLM & Cost Enforcement

* Default LLM: **OpenAI `o4-mini`**.
* `shared/oai_client.py`:

  * Single client for sending requests to OpenAI (both agents share this).
  * Integrated with `shared.token_cost_tracker.TokenCostTracker`.
* `TokenCostTracker`:

  * Moved from `computer_use_agent/utils` to `shared/token_cost_tracker.py`.
  * Tracks:

    * `input_cached_tokens`, `input_new_tokens`, `output_tokens`.
    * Per-call and cumulative cost for each model.
* The planner:

  * After each call to `o4-mini`, calls `TokenCostTracker.record_response(...)`.
  * Reads cumulative cost for the current run and updates `estimated_llm_cost_usd`.
  * If `estimated_llm_cost_usd > budget.max_llm_cost_usd`:

    * Stops immediately.
    * Returns `MCPTaskResult` with `success=False` and a clear “LLM budget exceeded” message.

---

### 11. Security Posture (MVP)

* **Redaction-first**:

  * Use `redact_payload` to mask sensitive fields before:

    * Logging,
    * Prompting,
    * Or persisting summaries.
* **Sandbox discipline**:

  * Planner prompt instructs:

    * No full document dumps.
    * No raw credential printing.
    * Prefer aggregates and sparse samples.
* **Local sandbox, restricted network**:

  * Sandbox has no general outbound network access; any external interactions go via MCP tools that are already governed by OAuth/composio.
* **Heavier features deferred**:

  * PII tokenization, fine-grained access control, and extensive audit logs are explicitly postponed until we have concrete customer/security requirements.

---

### 12. External Interfaces

* v1 interface is **library-only**:

  * Consumers call `mcp_agent.planner.execute_mcp_task(...)` directly.
  * Primary consumers:

    * Computer-use agent (desktop/GUI worker).
    * Orchestrator/background workers.
    * Tests and internal scripts.
* CLI / REST:

  * Deferred until the planner API stabilizes.
  * When added, both will be **thin shells** over `execute_mcp_task()` so they don’t fork logic.

---

### 13. Migration Tasks

1. **Shared infra extraction**

   * Move `token_cost_tracker.py` → `shared/token_cost_tracker.py`.
   * Move `logger.py` (or equivalent shared logging utilities) → `shared/logger.py`.
   * Move `oai_client.py` from `computer_use_agent` to `shared/oai_client.py`.
   * Update imports across:

     * `computer_use_agent`.
     * `mcp_agent`.
     * Any other modules using these utilities.

2. **TypeScript deprecation**

   * Remove `toolbox/typescript.py` and all TS sandbox code.
   * Remove TS-related fields/stats from `ToolboxBuilder.persist()`.

3. **Python codegen**

   * Add `PythonGenerator` and templates:

     * `sandbox_py/client.py` template.
     * Per-provider/per-tool wrapper templates.
   * Wire `ToolboxBuilder.persist()` to call `PythonGenerator.write()` and track `py_files`.

4. **Sandbox runner**

   * Implement `run_python_plan()` and `SandboxResult` types.
   * Implement bridging between sandbox `call_tool()` and `MCPAgent/MCPClient`.

5. **Planner**

   * Implement `mcp_agent.planner` with:

     * Canonical **planner prompt** (developer-as-system).
     * Context manager & trimming.
     * Budget enforcement and cost tracking.
     * Discovery, direct tool path, and sandbox path.
     * Telemetry emission.

6. **Tests**

   * Add unit tests for:

     * Python codegen (snapshots).
     * Summarization + redaction behavior.
     * Sandbox runner (success, failure, timeout).
     * Planner loop behavior with budget enforcement and both execution modes.
   * Add integration tests simulating realistic Gmail/Slack workflows.

---

### 14. Outstanding Questions (Resolved)

* **Provider scope:** Start with Composio-backed Gmail & Slack; architecture supports fast expansion without planner changes.
* **Sandbox strategy:** MVP uses local Python subprocesses with a stable `run_python_plan()` interface, paving the way for remote/containerized execution.
* **LLM & cost:** Standardize on `o4-mini`, centralize cost tracking via `shared.token_cost_tracker`, and enforce `max_llm_cost_usd` at the planner level.
* **Security posture:** Rely on redaction + sandbox discipline for MVP; escalate to stronger mechanisms as needed.
* **External interface:** Library-only entry point `execute_mcp_task()` for now; CLI/REST later.
* **TypeScript deprecation:** All tool codegen and sandbox logic are now Python-only.
* **Prompt model:** System prompt is deprecated; the **developer/planner prompt is the single canonical instruction layer** used to control the agent.

This final plan reflects the fully Python, modular, and shared-infra design for the Standalone MCP Agent, with all your latest augmentations baked in.
