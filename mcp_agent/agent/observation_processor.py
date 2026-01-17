"""Task-aware observation extraction using LLM summarization.

This module extracts task-relevant information from large tool and sandbox results.
No legacy truncation fallback - we fail fast if LLM is unavailable.
"""

import json
from typing import Any, TYPE_CHECKING

from shared.llm_client import LLMClient, extract_assistant_text
from mcp_agent.utils.token_counter import count_json_tokens

if TYPE_CHECKING:
    from mcp_agent.agent.state import AgentState


SUMMARIZATION_SYSTEM_PROMPT = """You are the “Task-Aware Action Result Extractor”.

GOAL
Given:
1) a plain-English TASK string
2) an ACTION_TYPE (e.g., "tool" or "sandbox")
3) the ACTION_INPUT payload used to produce the result
4) a large ACTION_RESULT JSON payload produced by an API/tool call or sandbox execution
Extract ONLY the information relevant to completing the TASK.

Do NOT preserve the original JSON structure. Do NOT copy large portions of the payload.

WHAT “RELEVANT” MEANS
Include data that directly helps the caller complete the TASK, such as:
- Primary entities referenced by the task (IDs, names, emails, URLs, timestamps, amounts, statuses)
- The specific fields needed to take the next action (record identifiers, required parameters, pagination tokens)
- Results, outcomes, and confirmations (created/updated item IDs, URLs, state transitions)
- Errors that block progress (error codes, messages, missing permissions, invalid fields) + any remediation hints present

USE INPUT PAYLOAD FOR INTERPRETATION
The ACTION_INPUT is not part of the “result,” but it helps you:
- interpret what the action attempted to do
- identify which returned fields matter
- detect mismatches (e.g., you asked to update X but result shows Y)

HIGHER LEVEL CONTEXT
The user message includes a HIGHER LEVEL TASK and a HIGHER LEVEL TRAJECTORY from the
orchestrator. They provide the broader goal and recent execution context for this run,
so you can judge what information from ACTION_RESULT_JSON is truly relevant. Use them
only to guide relevance and selection; do not treat them as new data or rewrite them.

EXCLUDE / DROP AGGRESSIVELY
- Formatting/styling/presentation metadata unless the task explicitly asks about it
- Repeated boilerplate, verbose logs, raw HTML, long text blocks not required for the task
- Entire arrays/objects unless the task explicitly needs them
- Any content not clearly connected to the TASK

SPECIAL HANDLING
- Search/list responses: include total counts + top relevant items (up to 5) + pagination tokens if present.
- Create/update/get responses: include key identifiers, status fields, and any URLs needed to reference the object.
- Error responses: include status code, error reason/message, and minimum context needed to debug.
- Nested huge arrays/objects: summarize as counts + a few representative/most relevant items (up to 5).

SELECTION RULES
- If many records exist, pick the ones most relevant to the TASK by exact/partial string match on names/emails/IDs and by recency if timestamps exist.
- If unsure what is relevant, prefer IDs, URLs, titles/names, status fields, and small excerpts (<= 200 chars each).

REDACTION
Never output secrets from either input or result: access tokens, refresh tokens, API keys, cookies, Authorization headers. Replace with “[REDACTED]”.

OUTPUT FORMAT (MUST FOLLOW)
Return VALID JSON ONLY (no markdown, no prose).
The JSON MUST be exactly:

{
  "success": boolean,
  "data": { ... },
  "error": boolean  // OPTIONAL; include only when an error was encountered
}

DATA OBJECT (keys omitted when not applicable)
data: {
  "status": "success" | "error" | "partial" | "unknown",

  "key_facts": { ... },
  "records": [ { ... } ],
  "excerpts": [ { "text": string, "path": string } ],
  "pagination": { "next_page_token": string|null, "has_more": boolean|null },

  "errors": [ { "code": string|null, "message": string, "path": string|null } ],

  "paths_used": [ string ],
  "omitted_summary": string,
  "missing": [ string ]                  // if status="partial"
}

SUCCESS / ERROR SEMANTICS
- If you can extract enough information to proceed: success=true; data.status="success" (or "unknown" if outcome can’t be determined).
- If the result clearly indicates failure OR you hit an extraction-blocking issue: success=false; data.status="error"; include top-level "error": true; populate data.errors.
- If you extracted some relevant info but not enough to proceed: success=true; data.status="partial"; include data.missing.
"""


def summarize_observation(
    payload: Any,
    payload_type: str,
    original_tokens: int,
    context: "AgentState",
    *,
    action_type: str,
    action_name: str | None,
    action_operation: str | None,
    task: str | None = None,
    reasoning: str | None = None,
    input_payload: Any = None,
    sandbox_code: str | None = None,
) -> Any:
    """
    Extract task-relevant information from a large observation.

    This function extracts task-relevant information from tool results or sandbox
    outputs using a task-aware summarization prompt.

    Args:
        payload: The data to summarize (dict, list, or other JSON-serializable)
        payload_type: "tool_result" or "sandbox_result" (for logging/metrics)
        original_tokens: Original token count (for calculating compression target)
        context: Agent state with token tracker and event recording helpers
        action_type: "tool" or "sandbox"
        action_name: Provider/tool name or sandbox label
        action_operation: Specific operation or tool name
        task: Initial task string (optional context)
        reasoning: Planner reasoning string for the step (optional context)
        input_payload: Tool input payload (tool_result only)
        sandbox_code: Sandbox code body (sandbox_result only)

    Returns:
        Summarized payload maintaining original structure

    Raises:
        ValueError: If payload cannot be serialized to JSON
        Exception: If LLM call fails - no fallback, fail fast

    Example:
        >>> large_result = {"messages": [...100 items...], "total": 100}
        >>> original_tokens = count_json_tokens(large_result)  # 12000
        >>> compressed = summarize_observation(large_result, "tool_result", original_tokens, ctx)
        >>> new_tokens = count_json_tokens(compressed)  # ~7200 (60% of original)
    """
    # Calculate target tokens to keep output bounded.
    target_tokens = int(original_tokens * 0.60)

    # Add 20% headroom to max_output_tokens to avoid mid-generation cutoff
    # This ensures the model has space to complete the JSON properly
    max_output = int(target_tokens * 1.2)

    # Serialize payload to JSON for LLM input
    try:
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        context.record_event(
            "mcp.observation_processor.serialization_error",
            {"error": str(e), "type": payload_type}
        )
        raise ValueError(f"Cannot serialize payload for summarization: {e}")

    def _stringify_context(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(value)

    def _stringify_prompt_context(value: Any) -> str:
        if value is None:
            return "None"
        if isinstance(value, str):
            return value or "None"
        return _stringify_context(value)

    if input_payload is None and sandbox_code:
        input_payload = {"code": sandbox_code}
    input_payload_json = _stringify_context(input_payload) if input_payload is not None else "null"
    action_block = (
        f"{{name: {json.dumps(action_name or '')}, "
        f"operation: {json.dumps(action_operation or '')}}}"
    )
    extra_context = context.extra_context if hasattr(context, "extra_context") else {}
    higher_level_task = None
    higher_level_trajectory = None
    if isinstance(extra_context, dict):
        higher_level_task = extra_context.get("orchestrator_task")
        higher_level_trajectory = extra_context.get("orchestrator_trajectory")
    higher_level_task_str = _stringify_prompt_context(higher_level_task)
    higher_level_trajectory_str = _stringify_prompt_context(higher_level_trajectory)

    # Build messages for LLM
    messages = [
        {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Extract task-relevant information from this action result.\n\n"
                f"TASK:\n{task or ''}\n\n"
                f"HIGHER LEVEL TASK:\n{higher_level_task_str}\n\n"
                f"HIGHER LEVEL TRAJECTORY:\n{higher_level_trajectory_str}\n\n"
                f"ACTION_TYPE:\n{action_type}\n\n"
                f"ACTION:\n{action_block}\n\n"
                f"ACTION_INPUT_PAYLOAD_JSON:\n{input_payload_json}\n\n"
                "REASONING BEHIND THE ACTION:\n"
                f"{reasoning or ''}\n\n"
                f"ACTION_RESULT_JSON:\n{payload_json}\n\n"
                "Requirements:\n"
                "- Output valid JSON only, following the output rules in the system instructions.\n"
                "- Do NOT copy the payload.\n"
                "- Use ACTION_INPUT only to interpret/prioritize what matters.\n"
                "- Include only the minimum info needed to proceed on the TASK.\n"
            )
        }
    ]

    # Create client and call LLM
    client = LLMClient(default_model="o4-mini")

    try:
        response = client.create_response(
            model="o4-mini",
            messages=messages,
            max_output_tokens=max_output,
            reasoning_effort="low",  # Fast inference for compression task
            text={"format": {"type": "json_object"}},  # Force JSON output
        )

        # Track tokens for this summarization call
        model_name = getattr(response, "model", None) or "o4-mini"
        context.token_tracker.record_response(
            model_name,
            f"observation.processor.{payload_type}",
            response
        )

        # Extract and parse response
        compressed_text = extract_assistant_text(response)
        if not compressed_text:
            raise ValueError("LLM returned empty response")

        compressed_payload = json.loads(compressed_text)

        # Calculate and log compression metrics
        compressed_tokens = count_json_tokens(compressed_payload)
        reduction_pct = ((original_tokens - compressed_tokens) / original_tokens) * 100

        context.record_event(
            "mcp.observation_processor.completed",
            {
                "type": payload_type,
                "original_tokens": original_tokens,
                "compressed_tokens": compressed_tokens,
                "reduction_percent": round(reduction_pct, 1),
                "target_tokens": target_tokens,
            }
        )

        return compressed_payload

    except json.JSONDecodeError as e:
        context.record_event(
            "mcp.observation_processor.invalid_json",
            {"error": str(e), "type": payload_type}
        )
        raise

    except Exception as e:
        context.record_event(
            "mcp.observation_processor.failed",
            {"error": str(e), "type": payload_type}
        )
        raise
