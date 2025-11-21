# Planner Prompt & Context Redesign Plan

## Goal
Restructure the standalone MCP planner’s prompts and developer context so the LLM receives structured state information without explicit budget prose, while planners and hosts continue to enforce budgets internally.

## Steps

1. **Audit Prompt + Developer Message Usage**  
   - Inspect `mcp_agent/planner/prompt.py` and `mcp_agent/planner/llm.py` to confirm where `PLANNER_PROMPT` and `_developer_message` strings are consumed.  
   - Verify that no other modules inject budget text so prompt updates remain localized.

2. **Redesign `PLANNER_PROMPT`**  
   - Replace the existing prompt with the detailed contract described in the spec: command schema, sandbox expectations, summaries, and strict JSON output instructions.  
   - Remove all budget references; emphasize structured planner state and sandbox guidance instead.

3. **Introduce Structured Planner State JSON**  
   - Add `PlannerContext.planner_state(snapshot)` returning a dict with task metadata, tool menu, summaries, search counts, extra context, and new `steps` history.  
   - Update `PlannerLLM._developer_message` to serialize this dict (deterministic JSON) instead of free-form prose.

4. **Record Detailed Step History**  
   - Add a `PlannerStep` dataclass and `steps: list[PlannerStep]` to `PlannerContext`.  
   - Implement `record_step(...)` and update runtime handlers (`_execute_tool`, `_execute_sandbox`, `_execute_search`, `_failure`, `_budget_failure`, finish path) to log previews, success flags, `result_key`, and errors.  
   - Include recent steps (e.g., last 10) in `planner_state`.

5. **Tag Summaries Explicitly**  
   - Extend `summarize_payload` outputs with fields like `is_summary: true` and clearer `notes` about truncation/persistence.  
   - Ensure `tool_summaries` and `sandbox_summaries` consume these new fields automatically when added to the planner state.

6. **Structure User Message Payload**  
   - Encode the user message as JSON: `{ "task": ..., "extra_context": ... }` to reinforce structured inputs.  
   - Adjust the system prompt text to explain this format so the model knows how to read it.

7. **Remove Budget Text from Prompts**  
   - Double-check `_developer_message` and `PLANNER_PROMPT` for any lingering budget sentences.  
   - Keep budget enforcement logic in `BudgetTracker`/telemetry so `execute_mcp_task` still terminates based on limits without exposing the numbers to the LLM.

8. **Update Tests & Snapshots**  
   - Revise or add unit tests covering `planner_state` shape, `record_step`, and summary tagging.  
   - Re-run planner contract/integration tests to ensure the loop still functions with the reworked prompts.  
   - Adjust any prompt snapshots or fixtures if they exist.

---

## Progressive-Disclosure Cleanup (Anthropic “Code Execution with MCP” Alignment)

1. **Prompt Reinforcement**
   - Update the system prompt to explicitly require natural-language `search` queries (e.g., “gmail inbox emails”) and to cap search calls (≤3) before sandboxing.
   - Remind the model that every MCP response has the `{successful, data, error}` envelope and must be inspected before using payloads.
   - Emphasize that sandbox code should do all branching/loops and only return aggregates or small samples (never bulk data).

2. **Planner State Reshape**
   - Replace the large `history` + `provider_tree` payload with a compact schema:
     - `task`
     - `tools_root` + `available_servers`
     - `history_summary` (short English recap)
     - `recent_steps` (last few entries only, with `type`, `status`, `summary`, optional storage refs)
   - Remove redundant fields (task IDs, full provider listings) from every turn; keep them static or accessible via search instead.

3. **Search Result Tiers**
   - For `detail_level: "summary"`, return only lightweight metadata (`tool`, `qualified_name`, `short_description`).
   - For `detail_level: "full"`, include detailed docstrings, parameter schemas, provider diagnostics.
   - Ensure both the simple name (`gmail_search`) and qualified name (`gmail.gmail_search`) are indexed so natural-language queries succeed.

4. **History / Code Persistence**
   - After each sandbox run, save the generated script under `skills/` (or similar) and store a pointer (`saved_to`) plus a one-line summary in planner state.
   - Drop the full code blocks from `recent_steps`; rely on saved files and summaries to keep the developer prompt small.

5. **Logging Hygiene**
   - Keep raw tool payloads inside `context.raw_outputs` (or persisted to disk) but only surface summarized previews in planner state/logs.
   - When search or sandbox results are empty, record concise summaries (e.g., “Fetched 0 messages”) instead of dumping entire response structures.

6. **Testing / Validation**
   - Add tests that snapshot the new `PLANNER_STATE_JSON` shape and enforce the absence of large provider/tool dumps.
   - Add regression tests to confirm search results honor the new detail tiers and that sandbox histories never exceed the recent-steps window.
