from __future__ import annotations

"""
LLM-backed translator that converts raw agent outputs and trajectories into the
canonical StepResult.output shape.

If the LLM call fails or is unavailable, we fall back to a deterministic,
compact summary constructed from the provided data.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from orchestrator_agent.data_types import AgentTarget, PlannedStep

try:  # Optional dependency
    from shared.oai_client import OAIClient, extract_assistant_text
except Exception:  # pragma: no cover
    OAIClient = None  # type: ignore
    extract_assistant_text = None  # type: ignore

logger = logging.getLogger(__name__)


TRANSLATOR_SYSTEM_PROMPT = """\
You are a translator that converts raw agent execution outputs into a canonical, structured format for an orchestrator to reason over.

## Your Role

You receive execution results from either:
1. **MCP Agent** - API-based tool execution with structured responses
2. **Computer-Use Agent** - Desktop UI automation with visual observations

Your task is to translate these into a **canonical dictionary format** that preserves all important data while organizing it consistently.

## Critical Rules

### Data Preservation
- **PRESERVE ALL retrieved/fetched data** (emails, API responses, database records, file contents)
- **KEEP tool outputs intact** - MCP already summarized large payloads, don't trim further
- **MAINTAIN step trajectories** - Include what was done and what was observed
- **INCLUDE diagnostic info** - Errors, reflections, behavior observations

### No Invention
- **NEVER fabricate** timestamps, IDs, counts, or numeric values
- **NEVER guess** error messages or API responses
- **USE ACTUAL VALUES** from the input or set to null if missing
- **QUOTE DIRECTLY** from agent outputs, don't paraphrase critical data

### Canonical Structure
Always output this exact JSON structure:
{
  "summary": "<1-2 sentence high-level outcome>",
  "success": true | false,
  "error": "<error message>" | null,
  "error_code": "<machine_readable_code>" | null,
  "details": [
    "<step 1: action and outcome>",
    "<step 2: action and outcome>",
    "..."
  ],
  "artifacts": {
    "tool_outputs": [...],         // MCP: API responses
    "ui_observations": [...],      // Computer-Use: UI changes observed
    "retrieved_data": {...},       // Data fetched (emails, records, etc.)
    "files_created": [...],        // Files/documents created
    "code_executed": [...]         // Code snippets executed
  },
  "raw_ref": "<provided raw reference>"
}

## Translation Guide by Agent

### MCP Agent Translation

**Input Structure Keys:**
- `success` (bool): Overall task success
- `final_summary` (str): Human-readable summary
- `error` (str|null): Error message if failed
- `error_code` (str|null): Error code (e.g., "auth_failed")
- `raw_outputs` (dict): Raw API responses from tools (already summarized)
- `steps` (list): Step-by-step execution history
  - Each step has: action_type, success, observation, action_outcome, error

**Mapping:**
1. **summary**: Use `final_summary` directly - it's already well-crafted
2. **success**: Copy `success` field as-is
3. **error**: Use `error` or `error_message` field
4. **error_code**: Copy `error_code` field
5. **details**: Extract from `steps[]`:
   - For search: "Searched {provider} for {query}, found {N} tools"
   - For tool: "Called {tool_id} with {params}, result: {outcome summary}"
   - For sandbox: "Executed Python code, {success/error}"
   - For finish: "{final summary}"
6. **artifacts.tool_outputs**: Copy relevant items from `raw_outputs` and `steps[].observation`
7. **artifacts.retrieved_data**: Extract actual data retrieved (emails, records, files, etc.)
   - **IMPORTANT**: For search results, include ONLY tool names/IDs in a "found_tools" array, NOT full tool specifications
   - Example search result: `{"found_tools": [{"tool_id": "gmail.gmail_search", ...}], "count": 5}`
   - The orchestrator only needs to know WHAT tools were retrieved / searched for, not their full schemas

### Computer-Use Agent Translation

**Input Structure Keys:**
- `status` (str): "success", "failed", or "timeout"
- `completion_reason` (str): "DONE", "FAIL", or "MAX_STEPS_REACHED"
- `steps` (list): List of execution steps
  - Each step has: step_index, plan, action, reflection, behavior_fact_answer, info.code_agent_output

**Mapping:**
1. **summary**: Synthesize from last step's plan + completion_reason
2. **success**: status == "success"
3. **error**: Extract from failure details if status == "failed"
4. **error_code**: Map completion_reason (FAIL → "task_failed", MAX_STEPS → "timeout")
5. **details**: For each step, combine:
   - "{step N}: {plan}"
   - "Action: {high-level action description}"
   - "Reflection: {reflection}" (if present)
   - "Observed: {behavior_fact_answer}" (if present)
6. **artifacts.ui_observations**: Extract behavior_fact_answer from all steps
7. **artifacts.code_executed**: Extract code_agent_output summaries from steps[].info

## Edge Cases

### Empty or Missing Fields
- If field is missing → use null or empty list/dict
- If summary is empty → synthesize from last step's details
- If no steps → details = ["No actions taken"]

### Errors and Failures
- ALWAYS include full error messages
- PRESERVE error_details if present
- Include failed step information in details array

### Large Data Payloads
- MCP: Already summarized by smart summarizer, keep as-is
- Computer-Use: Already text-only trajectory, keep full stepwise details
- Only truncate artifacts if individual items exceed 5000 tokens

## Output Requirements

1. **Always return valid JSON**
2. **Always include all required fields** (summary, success, error, error_code, details, artifacts, raw_ref)
3. **Never return empty summary** - synthesize from steps if needed
4. **Preserve data types** (booleans as booleans, not strings)
5. **Use null for missing values**, not undefined or omitted fields

## Quality Checklist

Before returning, verify:
- All retrieved data is preserved (emails, API responses, etc.)
- No invented timestamps, IDs, or numeric values
- Step trajectory is clear and complete
- Error information is detailed (if applicable)
- Artifacts contain relevant outputs
- Summary accurately reflects what happened
- JSON is valid and follows canonical structure
"""


def _build_messages(
    task: str,
    step: PlannedStep,
    target: AgentTarget,
    trajectory: List[str],
    raw_preview: str,
) -> List[Dict[str, Any]]:
    user_payload = {
        "task": task,
        "step": {
            "target": target,
            "next_task": step.next_task,
            "verification": step.verification,
            "description": step.description,
        },
        "trajectory": trajectory,
        "raw_preview": raw_preview,
        "instructions": (
            "Return JSON with keys: summary (string), success (bool), "
            "error (string|null), error_code (string|null), "
            "details (list of short strings), artifacts (list or dict), raw_ref (string or null). "
            "Do NOT include IDs or token/cost data."
        ),
    }
    return [
        {"role": "system", "content": TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def _safe_json_load(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None


def translate_step_output(
    *,
    task: str,
    step: PlannedStep,
    target: AgentTarget,
    trajectory: List[str],
    raw_result: Dict[str, Any],
    raw_ref: Optional[str] = None,
    llm_client: Optional[Any] = None,
    llm_model: str = "o4-mini",
    max_output_tokens: int = 10000,
) -> Dict[str, Any]:
    """
    Translate raw agent output into canonical shape via LLM, with deterministic fallback.
    """
    logger.info(
        "translator.enter target=%s step=%s preview_len=%s",
        target,
        getattr(step, "step_id", None),
        len(json.dumps(raw_result, ensure_ascii=False)),
    )
    # Increase preview size to 8000 chars to preserve more data
    # MCP agent already applies smart summarization, so this should be safe
    raw_preview = json.dumps(raw_result, ensure_ascii=False)[:8000]
    client = llm_client
    if client is None and OAIClient is not None:
        try:
            client = OAIClient()
            logger.info("translator.llm_client_ready target=%s", target)
        except Exception:
            logger.info("translator.llm_client_unavailable target=%s", target)
            client = None

    if client:
        try:
            messages = _build_messages(task, step, target, trajectory, raw_preview)
            response = client.create_response(
                messages=messages,
                model=llm_model,
                max_output_tokens=max_output_tokens,
                reasoning_effort="low",
            )
            text = None
            if extract_assistant_text is not None:
                try:
                    text = extract_assistant_text(response)
                except Exception:
                    text = None
            if not text:
                text = getattr(response, "output_text", None) or getattr(
                    response, "text", None
                )
            if isinstance(text, str):
                parsed = _safe_json_load(text)
                if parsed:
                    parsed.setdefault("raw_ref", raw_ref)
                    # Ensure MCP raw outputs are preserved even when LLM succeeds
                    if target == "mcp":
                        raw_outputs = raw_result.get("raw_outputs") or {}
                        if raw_outputs:
                            artifacts = parsed.get("artifacts")
                            if not isinstance(artifacts, dict):
                                artifacts = {}
                            # Attach raw outputs for downstream context
                            rd = artifacts.get("retrieved_data")
                            if not isinstance(rd, dict):
                                rd = {}
                            # Prefer existing tool_outputs, else use raw_outputs
                            if "tool_outputs" not in artifacts or not artifacts["tool_outputs"]:
                                artifacts["tool_outputs"] = raw_outputs
                            parsed["artifacts"] = artifacts
                    logger.info("translator.llm_success target=%s", target)
                    return parsed
            logger.info("translator.llm_parse_failed target=%s", target)
        except Exception as exc:  # pragma: no cover
            logger.info("translator.llm_error target=%s error=%s", target, exc)

    # Deterministic fallback - preserve data from MCP or computer-use agents
    logger.info("translator.fallback target=%s", target)
    details = trajectory[-5:] if trajectory else []

    # Build artifacts from raw_result
    artifacts = {}
    summary = raw_result.get("final_summary") or raw_result.get("summary")
    success_flag = bool(raw_result.get("success", True))
    error_val = raw_result.get("error")
    error_code_val = raw_result.get("error_code")

    if target == "mcp":
        # For MCP: Extract from raw_outputs and steps
        raw_outputs = raw_result.get("raw_outputs", {})
        steps = raw_result.get("steps", [])

        # Preserve tool outputs
        if raw_outputs:
            artifacts["tool_outputs"] = [
                {"tool": k, "result": v} for k, v in list(raw_outputs.items())[:10]
            ]

        # Extract retrieved data from steps (sandbox outputs, tool observations)
        retrieved_data = {}
        for step_item in steps:
            action_type = step_item.get("action_type")
            outcome = step_item.get("action_outcome", {})

            # Special handling for search results
            if action_type == "search":
                # For search, observation contains the full found_tools array
                observation = step_item.get("observation")
                if observation and isinstance(observation, list):
                    # Extract compact info: tool IDs and count
                    retrieved_data["found_tools"] = observation
                    retrieved_data["count"] = outcome.get("total_found", len(observation))
            else:
                # For non-search, extract from action_outcome
                if isinstance(outcome, dict):
                    retrieved_data.update(outcome)

        # Always attach raw outputs so downstream prompts see full data
        if retrieved_data:
            artifacts["retrieved_data"] = retrieved_data

    elif target == "computer_use":
        # For computer-use: Extract UI observations from steps
        steps = raw_result.get("steps", [])
        ui_observations = []
        code_executed = []
        retrieved_data: Dict[str, Any] = {}

        for step_item in steps:
            if isinstance(step_item, dict):
                # Extract behavior observations
                behavior = step_item.get("behavior_fact_answer")
                if behavior:
                    ui_observations.append(behavior)

                # Extract code execution
                exec_result = step_item.get("execution_result")
                if exec_result:
                    code_executed.append(str(exec_result)[:200])

        status = raw_result.get("status")
        completion_reason = raw_result.get("completion_reason")

        if status:
            retrieved_data["status"] = status
            # Treat non-failed statuses as successful unless explicit error
            if status in {"failed", "error", "stopped"}:
                success_flag = False
        if completion_reason:
            retrieved_data["completion_reason"] = completion_reason

        if ui_observations:
            artifacts["ui_observations"] = ui_observations[:10]
            retrieved_data["last_ui_observation"] = ui_observations[-1]
            # Use the most recent observation as a summary if none provided
            if not summary:
                summary = ui_observations[-1]
        if code_executed:
            artifacts["code_executed"] = code_executed[:10]
        if retrieved_data:
            artifacts["retrieved_data"] = retrieved_data

    # Override with existing artifacts if present
    if raw_result.get("artifacts"):
        artifacts = raw_result.get("artifacts")

    if not summary:
        # Fall back to details or the planned step description
        summary = (
            details[-1]
            if details
            else step.description
            or step.next_task
        )

    return {
        "summary": summary,
        "success": success_flag,
        "error": error_val,
        "error_code": error_code_val,
        "details": details,
        "artifacts": artifacts,
        "raw_ref": raw_ref,
    }


__all__ = ["translate_step_output", "TRANSLATOR_SYSTEM_PROMPT"]
