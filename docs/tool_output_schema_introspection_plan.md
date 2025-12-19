# Tool Output Schema: Lazy Introspection Plan (IDE Pattern)

## TL;DR

Our MCP agent currently discovers tools via `search_tools(...)` and shows the planner a compact tool descriptor that includes `output_fields` (a flattened list of output schema paths). For tools with large output schemas, we hard-cap the number of emitted fields, which frequently hides key fields the planner needs. A naive fix is schema pagination, but that introduces an N+1 round-trip problem, context fragmentation, and arbitrary semantic cuts.  

This plan replaces pagination with an “IDE introspection” pattern:

1. **Eager summary**: Keep `output_fields` compact, but make it *heuristically pruned* and *hierarchically folded* (importance-aware + top-level structure + “fold” markers that say what’s hidden).
2. **Lazy drill-down**: Add a dedicated, always-available tool `inspect_tool_output(tool_id, field_path=...)` that returns the schema slice for exactly the subtree the planner needs.

This keeps common cases O(1) turns (summary → plan) and makes deeper understanding possible without forcing sequential “page fetches”.

---

## 0) Implementation Lock-Ins (Finalized)

This document is implementation-ready. The previously-open decisions are locked as follows:

- **Discovery friction**: Use **Preload** (Option A) — `toolbox.inspect_tool_output` is injected into `available_tools` in `mcp_agent/agent/state.py:build_planner_state(...)` so the planner can call it without running an extra search.
- **Tier 1 selection**: Standardize the Tier 1 regex used by the schema summarizer:
  - `TIER_1_REGEX = r"(?:^|\\.|\\[\\]\\.)(id|.*_id|name|title|status|type|url|email|price|amount|created|updated|timestamp)$"`
- **Summary budget**: Keep the current context budget for schema summaries:
  - `MAX_SUMMARY_FIELDS = 30`

---

## 1) Current System (What exists today)

### 1.1 Codebase mental model (relevant parts)

- **Planner loop**: `mcp_agent/agent/run_loop.py` orchestrates “search / tool / sandbox / finish / fail”.
- **Tool discovery**:
  - Initial inventory shown as `provider_tree`: `mcp_agent/knowledge/search.py:get_inventory_view(...)`.
  - Discovery command: `type="search"` → executed by `mcp_agent/agent/executor.py:_execute_search(...)`.
  - Search implementation: `mcp_agent/knowledge/search.py:search_tools(...)`.
- **Tool descriptors**:
  - Returned as **compact descriptors** (min context): `mcp_agent/knowledge/types.py:ToolSpec.to_compact_descriptor()`.
  - `output_fields` is produced by flattening a JSON-schema-like dict: `mcp_agent/knowledge/utils.py:flatten_schema_fields(...)`.
  - Current caps: `max_depth=3`, `max_fields=30` (hard truncation).
- **Planner prompt contract**:
  - Prompt: `mcp_agent/agent/prompts.py:PLANNER_PROMPT`.
  - It instructs the model to use `output_fields` to safely index into tool outputs under `data`.

### 1.2 The specific problem

Some tools have output schemas with **hundreds or thousands** of leaf fields (e.g., Shopify entities, Google Docs document structure). Today we emit only the first ~30 flattened leaf paths, so:

- Key fields may not appear in `output_fields`.
- The planner may not realize a field exists, or may guess wrong paths/types.
- This hurts reliability: wrong indexing, wrong extraction, wrong planning.

---

## 2) Why “Schema Pagination” Is a Trap (Engineering critique)

Treating the schema as a paginated API (Page 1 / Page 2 / Page 3) fixes the hard-cap but introduces:

1. **N+1 / round-trip latency**: The agent may need multiple LLM turns just to “read docs” before acting.
2. **Context fragmentation**: The model must remember Page 1 while looking at Page 2; this is brittle.
3. **Semantic breaking**: Arbitrary cuts can split nested objects mid-structure, destroying relationships.

This is especially harmful in agentic loops where extra turns increase failure probability.

---

## 3) Target Architecture: “Hierarchical Folding + Drill-Down” (IDE pattern)

### 3.1 Principles

1. **Summarize eagerly**:
   - Always include “Tier 1” fields (identifiers and common pivot fields) even in huge schemas.
   - Include “Tier 2” structure: top-level keys and the presence/type of nested containers.
   - Do **not** enumerate the “long tail” of deep nested fields by default.

2. **Introspect lazily**:
   - When the planner needs details (e.g., what’s inside `variants[]`), it calls an inspector tool.
   - This is random-access; the agent asks for exactly what it needs.

3. **Never hide the fact that data is hidden**:
   - Emit per-branch fold/overflow markers, e.g. either:
     - Fold line with context + drill-down hint: `variants[]: object (contains 15 sub-fields; inspect_tool_output(..., field_path="variants[]"))`, or
     - Explicit wildcard overflow marker after emitting some fields: `body.* (+12 more fields; inspect_tool_output(..., field_path="body"))`.
   - Add a descriptor-level boolean: `has_hidden_fields: true`.

### 3.2 Outcome

- Most tasks: **search → pick tool → call tool** (no extra schema turns).
- Complex tasks: **search → inspect specific branch → plan** (one targeted “doc lookup” turn).

---

## 4) Proposed Interface Changes (Minimal + Backwards-Compatible)

### 4.1 Compact tool descriptor changes (LLM-facing)

Current shape (per `PLANNER_PROMPT`) includes:

- `tool_id`, `server`, `signature`, `description`, `input_params`, `output_fields`

Add:

- `has_hidden_fields: bool`  
  Meaning: `true` if the descriptor is a summarized view (i.e., not all possible fields are enumerated).

Keep:

- `output_fields: list[str]` (do not change the *type*, only the *content strategy*)

### 4.2 `output_fields` content strategy (folded representation)

**Smart Summary Contract (format specification):**

1. **Primitives:** `key: type` (e.g., `status: string`)
2. **Fold markers:** `key: type (contains N sub-fields; inspect_tool_output(..., field_path="key"))`
3. **Tier 1 fields:** Always visible (IDs, names, statuses; see `TIER_1_REGEX`)
4. **Tier 2 fields:** Top-level keys (always visible)
5. **Tier 3 fields:** Nested fields (folded by default unless budget allows)

Instead of a flat “first N leaf paths” cut-off, `output_fields` becomes a **mixed list** of:

1. **Kept leaf fields** (Tier 1 + selected Tier 2/3), e.g.:
   - `id: string`
   - `status: string`
   - `customer.email: string`

2. **Fold markers** for large containers, e.g.:
   - `variants[]: object (contains 15 sub-fields; inspect_tool_output(tool_id="shopify.get_order", field_path="variants[]"))`
   - `body: object (contains 8 sub-fields; inspect_tool_output(..., field_path="body"))`
   - or wildcard overflow style: `body.* (+12 more fields; inspect_tool_output(..., field_path="body"))`

Notes:
- “contains N sub-fields” should be **immediate children count** (object properties or array item properties), not total deep leaves; it’s more stable and semantically meaningful.
- If children are unknown (e.g., `additionalProperties: true`), output:
  - `metadata: object (unknown keys; inspect_tool_output(...))`

### 4.3 New tool: `inspect_tool_output`

Expose a first-class “inspector” tool callable by the planner:

**Tool name (recommended):**
- Provider/server: `toolbox`
- Tool function: `inspect_tool_output`
- Tool id: `toolbox.inspect_tool_output`

**Inputs:**
- `tool_id: str` (e.g., `"shopify.shopify_get_order"`)
- `field_path: str | null` (dot notation; arrays use `[]`, e.g., `"variants[]"` or `"variants[].inventory_item"`)
- Optional caps:
  - `max_depth: int = 4` (how deep to summarize the returned subtree)
  - `max_fields: int = 120` (max flattened fields to return in the response)

**Output (data payload) should be compact and “planner-friendly”:**
```json
{
  "tool_id": "shopify.shopify_get_order",
  "field_path": "variants[]",
  "node_type": "object",
  "children": [
    {"name": "sku", "type": "string"},
    {"name": "price", "type": "string"},
    {"name": "inventory_item_id", "type": "string"}
  ],
  "flattened_fields": [
    "sku: string",
    "inventory_item_id: string",
    "inventory_management: string"
  ],
  "total_child_fields": 15,
  "truncated": true
}
```

Key points:
- `children` is immediate properties of the requested node (or array item properties).
- `flattened_fields` is a deeper preview (useful when children are nested).
- Always include `truncated` so the model knows when to drill further.

---

## 5) Detailed Implementation Plan (Step-by-step, with exact code touchpoints)

### Step 0 — Decide constants and format (one-time)

Define constants in one place (recommended: `mcp_agent/knowledge/utils.py` or a new `mcp_agent/knowledge/schema_summarizer.py`):

- `MAX_SUMMARY_FIELDS = 30` (keep current summary budget)
- `DEFAULT_SUMMARY_MAX_DEPTH = 3`
- `DEFAULT_INSPECT_MAX_FIELDS = 120`
- `DEFAULT_INSPECT_MAX_DEPTH = 4`

Standardized Tier 1 regex (locked; used by the summarizer):
- `TIER_1_REGEX = r"(?:^|\\.|\\[\\]\\.)(id|.*_id|name|title|status|type|url|email|price|amount|created|updated|timestamp)$"`

### Step 1 — Implement heuristic pruning + folding (no pagination)

**Where:**
- `mcp_agent/knowledge/utils.py`
- `mcp_agent/knowledge/types.py:ToolSpec.to_compact_descriptor`

**Approach:**
1. Add a new function that returns `(output_fields, has_hidden_fields)`:
   - `summarize_schema_for_llm(schema: dict, *, max_depth: int, max_fields: int) -> tuple[list[str], bool]`

2. Inside summarization:
   - Normalize schema root to the tool’s `data` schema (mirroring `flatten_schema_fields` behavior).
   - Extract immediate children of root (`properties`), and determine for each:
     - primitive: emit `key: <type>`
     - object: emit `key: object (contains N sub-fields; inspect_tool_output(..., field_path="key"))`
     - array:
       - if items are object: emit `key[]: object (contains N sub-fields; inspect_tool_output(..., field_path="key[]"))`
       - if items primitive: emit `key[]: <type>`

3. Tiering / selection:
   - Collect all **Tier 1** matches greedily (unlimited depth scan, but enforce a safety cap on visited schema nodes for performance).
   - Collect all **Tier 2** fields (immediate children of the root `data` object).
   - Output ordering (ensures structural cues are always visible even when Tier 1 is large):
     1) Tier 2 structural fields / fold markers (deduped), then
     2) Tier 1 leaf fields (deduped)
   - If `len(Tier1 + Tier2) < MAX_SUMMARY_FIELDS`, fill remaining budget with a **BFS** traversal of deeper fields (Tier 3), stopping when the budget is exhausted.
   - **Folding rule**: for any object/array that is not fully enumerated within the budget, emit the fold marker:
     - `f\"{key}: {type} (contains {child_count} sub-fields; inspect_tool_output(..., field_path='{path}'))\"`

4. `has_hidden_fields`:
   - `true` if any fold markers were emitted **or** if total flattened leaves up to some ceiling exceed emitted field count.

**Minimal-change constraint:**
- Do not change the type of `output_fields`; keep it `list[str]`.
- Keep existing `flatten_schema_fields(...)` unchanged for other callers; implement the new summarizer separately to avoid subtle regressions.

### Step 2 — Add `has_hidden_fields` to the compact descriptor

**Where:**
- `mcp_agent/knowledge/types.py:CompactToolDescriptor`
- `mcp_agent/knowledge/types.py:ToolSpec.to_compact_descriptor()`

**Changes:**
- Add a new field to `CompactToolDescriptor`:
  - `has_hidden_fields: bool`
- Update `to_dict()` to include it.
- Update `ToolSpec.to_compact_descriptor()` to call `summarize_schema_for_llm(...)` instead of calling `flatten_schema_fields(...)` directly.

**Notes:**
- Keep `output_fields` length small and predictable (default 30) to preserve context budgets.

### Step 3 — Implement the `inspect_tool_output` tool (lazy drill-down)

**Where (recommended):**
- New file: `mcp_agent/actions/wrappers/toolbox.py`

**Implementation sketch:**
1. Function signature:
   ```python
   def inspect_tool_output(context: AgentContext, tool_id: str, field_path: str = "", max_depth: int = 4, max_fields: int = 120) -> ToolInvocationResult:
       ...
   ```
2. Resolve the target tool schema:
   - Use `get_index(context.user_id)` and `index.get_tool(tool_id)` to retrieve `ToolSpec`.
   - Read `ToolSpec.output_schema`.
   - Normalize to the `data` subtree.
3. Navigate to `field_path`:
   - Parse segments:
     - `foo` means object property `foo`
     - `foo[]` means array `foo` and then traverse into `items`
     - `foo[].bar` means into array items then property `bar`
   - For each segment, traverse via JSON schema keys:
     - objects: `properties[name]`
     - arrays: `items`
4. Build compact result:
   - Determine node type (`object`, `array`, primitive).
   - Compute immediate children list (names + types).
   - Compute a flattened preview list for the subtree (bounded by `max_fields`, `max_depth`).
   - Return envelope `{successful: True, data: {...}}`.
5. Tool’s own `__tb_output_schema__`:
   - Provide a small schema for the inspector output itself so it also appears nicely in discovery outputs if needed.

**Safety/caps:**
- Never return the full raw JSON schema unbounded.
- Always enforce `max_fields`/`max_depth`.
- Return `truncated: true` when you hit caps.

### Step 4 — Make the `toolbox` provider always available (no OAuth)

We must ensure the toolbox provider appears as “authorized” so it shows up in:
- `get_inventory_view(...)` (provider_tree)
- `ToolboxBuilder` / manifest / index
- `search_tools(...)`

**Minimal change:**
- Special-case `OAuthManager.auth_status(context, provider)` in `mcp_agent/registry/oauth.py`:
  - If `provider == "toolbox"`, return `{authorized: True, configured: True, mcp_url: None, refresh_required: False, reason: None, ...}`.

This avoids touching the broader registry code and keeps toolbox tools purely local.

### Step 5 — Ensure the inspector is usable without “search friction”

Today, the executor blocks tool calls that were not discovered via search *only after* at least one search has occurred. This can create awkward flow:
1) search for “gmail inbox”
2) now wants inspect → must search again to “discover” toolbox tool

**Final decision: Preload (Option A).**

- In `mcp_agent/agent/state.py:build_planner_state(...)`, ensure `available_tools` always begins with the compact descriptor for `toolbox.inspect_tool_output` when present in the index and not already included.
- This should be implemented as a *non-mutating* injection into the planner payload (i.e., construct the returned `available_tools` list with the inspector prepended, without altering `self.search_results`).
- Rationale: removes the “search to find the inspector” turn and makes drill-down deterministic.

(Option B — executor exemption — is explicitly not chosen.)

### Step 6 — Update the MCP planner prompt to teach folding + introspection

**Where:**
- `mcp_agent/agent/prompts.py:PLANNER_PROMPT`

**Additions (precise):**
- Explain `has_hidden_fields`:
  - If true, `output_fields` is a summary; not all fields are listed.
- Explain fold markers:
  - Lines like `variants[]: object (contains 15 sub-fields; inspect...)` mean the container exists but is folded.
- Add instruction:
  - “If you need the structure of a folded field to write correct code, call `toolbox.inspect_tool_output` before proceeding.”
- Add a minimal tool-call example (as planner JSON):
  ```json
  {
    "type": "tool",
    "tool_id": "toolbox.inspect_tool_output",
    "server": "toolbox",
    "args": {"tool_id": "shopify.shopify_get_order", "field_path": "variants[]"},
    "reasoning": "Need variant fields to extract inventory status correctly."
  }
  ```

**Insert this directive block (verbatim) into the tool usage section:**

> **Handling Large Outputs:**
> Some tools have large output schemas that are summarized.
> * If you see a field marked like `variants[]: object (contains 15 sub-fields; inspect...)`, it means the details are hidden.
> * **Rule:** If you need to access a hidden field to write your plan (e.g., checking a specific variant attribute), you MUST first call `toolbox.inspect_tool_output(tool_id, field_path)` to see the structure. Do not guess paths.

### Step 7 — Update inventory view (optional)

`get_inventory_view(...)` is intentionally “tool names only”. With introspection we do not need pages, but we do want the model to know the toolbox provider exists.

If toolbox is part of `SUPPORTED_PROVIDERS`, it will already show up automatically once authorized. No further changes needed.

If we decide **not** to include toolbox in `SUPPORTED_PROVIDERS`, then we must explicitly inject it into inventory (but that is more invasive).

### Step 8 — Validation (scripts + automated checks)

**Update the smoke script:**
- `scripts/test_search_output.py` currently assumes `max_fields=30` and compares directly to wrapper flattening.
- Update it to:
  - Print and verify `has_hidden_fields`.
  - Detect fold markers (`"(contains"` / `"inspect_tool_output"`).
  - Optionally call `toolbox.inspect_tool_output` (direct Python invocation) for a folded path and print returned children.

**Add a new focused script (recommended):**
- `scripts/test_inspect_tool_output.py`
  - Inputs: `--tool-id`, `--field-path`
  - Prints inspector output JSON
  - Useful for debugging and prompt iteration.

**Concrete smoke verification (implementation-ready checklist):**
1. Use a known-large schema (e.g., `shopify_get_orders_with_filters_output_schema`) and run `summarize_schema_for_llm`:
   - Assert `has_hidden_fields is True`.
   - Assert fold markers are present (contain `contains` and `inspect_tool_output`).
2. Run `toolbox.inspect_tool_output` on a folded path (e.g., `field_path="orders[]"` or a nested branch under it):
   - Assert `children` is non-empty for object/array-of-object nodes.
   - Assert `flattened_preview` (or equivalent) respects `max_depth`/`max_fields` caps.
3. OAuth verification note (Shopify): user id `8cb7cbf2-f7a6-473a-920f-b6d2b9cc0c8d` has Shopify OAuth already configured; use it for end-to-end manual validation if needed.

**Optional unit tests** (if/where tests exist):
- Add a small pure-function test for schema path navigation and folding counts (no network).

---

## 6) Edge Cases / Correctness Notes

1. **Envelope vs `data`**
   - Many wrapper schemas include `{"properties": {"data": ...}}`. Both the summarizer and inspector must treat `data` as the root.

2. **`additionalProperties`**
   - If an object doesn’t declare `properties`, treat it as unknown:
     - fold marker: `foo: object (unknown keys; inspect...)`
     - inspector: `children=[]`, `note="additionalProperties"` or similar.

3. **Schema unions (`anyOf`/`oneOf`)**
   - If present, pick a best-effort type label (`"union"`) and show children only if determinable; otherwise encourage inspection.

4. **Arrays of arrays**
   - Preserve the `[]` semantics; allow `foo[][]` in parsing (or normalize to repeated segments).

5. **Stability**
   - Tier 1 always-kept fields should be stable across schema edits.
   - Fold markers should use immediate child counts to avoid huge, volatile numbers.

---

## 7) Rollout Strategy / Backwards Compatibility

- Keep `output_fields` as a list of strings to avoid breaking prompt parsing and downstream assumptions.
- Introduce `has_hidden_fields` as additive.
- Teach the planner prompt to treat `output_fields` as a summary and to use the inspector when needed.
- Optionally log events (e.g., `mcp.schema.inspect.called`) to measure adoption and identify tools with high inspection frequency.

---

## 8) Decision Log (Explicit)

**We will:**
- Keep the existing compact descriptor pipeline.
- Replace hard truncation of leaf fields with heuristic pruning + fold markers.
- Add `has_hidden_fields`.
- Add a dedicated `toolbox.inspect_tool_output` tool for drill-down.

**We will not:**
- Implement schema pagination (`output_fields_page`, `total_pages`).
- Dump full schemas into prompts or tool outputs.
