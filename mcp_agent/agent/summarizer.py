"""LLM-based payload summarization for tool and sandbox results."""

import json
from typing import Any, TYPE_CHECKING

from shared.oai_client import OAIClient, extract_assistant_text
from mcp_agent.utils.token_counter import count_json_tokens

if TYPE_CHECKING:
    from mcp_agent.agent.state import AgentState


SUMMARIZATION_SYSTEM_PROMPT = """You are a data compression assistant that reduces JSON payload sizes while preserving structure and key information.

Your task is to compress JSON data to approximately 35-40% of its original size while:

1. STRUCTURE PRESERVATION:
   - Keep all top-level keys exactly as they are
   - Maintain the JSON schema/shape (objects stay objects, arrays stay arrays)
   - Preserve all field names and types

2. CONTENT COMPRESSION:
   - Long strings (>100 chars): Extract key phrases, important entities, and core meaning
   - Arrays with many items: Keep first 2-3 representative items + total count
   - Nested objects: Preserve structure but compress inner content
   - Numbers/booleans/null: Keep exactly as-is, never change
   - Timestamps/IDs: Keep exactly as-is
   - Empty strings/arrays/objects: Keep as-is

3. INFORMATION PRIORITY:
   - Preserve: counts, totals, statuses, IDs, timestamps, error messages
   - Compress: long text descriptions, verbose logs, repeated patterns
   - Remove: redundant information, verbose formatting

4. OUTPUT FORMAT:
   - Return valid JSON only (no markdown, no explanations)
   - Match the input's JSON structure exactly
   - Ensure all keys from input appear in output

Example compression:
Input: {"messages": [{"id": "123", "text": "This is a very long email about quarterly business results with detailed financial information and many paragraphs of analysis that could be summarized...", "sender": "john@example.com"}, {"id": "124", "text": "Another long message...", "sender": "jane@example.com"}, ...30 more items...], "total": 31, "nextPageToken": "abc123"}

Output: {"messages": [{"id": "123", "text": "Quarterly business results, financial info summary", "sender": "john@example.com"}, {"id": "124", "text": "Another message summary", "sender": "jane@example.com"}, "<28 more items omitted>"], "total": 31, "nextPageToken": "abc123"}

Compress aggressively but preserve all structural information."""


def summarize_with_llm(
    payload: Any,
    payload_type: str,
    original_tokens: int,
    context: "AgentState",
) -> Any:
    """
    Summarize a large payload using LLM while maintaining JSON structure.

    This function compresses large JSON payloads (tool results or sandbox outputs)
    to approximately 60% of their original size while preserving the complete
    structure/shape. It uses o4-mini with low reasoning effort for fast inference.

    Args:
        payload: The data to summarize (dict, list, or other JSON-serializable)
        payload_type: "tool_result" or "sandbox_result" (for logging/metrics)
        original_tokens: Original token count (for calculating compression target)
        context: Agent state with token tracker and event recording helpers

    Returns:
        Summarized payload maintaining original structure

    Raises:
        ValueError: If payload cannot be serialized to JSON
        Exception: If LLM call fails (caller should handle fallback)

    Example:
        >>> large_result = {"messages": [...100 items...], "total": 100}
        >>> original_tokens = count_json_tokens(large_result)  # 12000
        >>> compressed = summarize_with_llm(large_result, "tool_result", original_tokens, ctx)
        >>> new_tokens = count_json_tokens(compressed)  # ~7200 (60% of original)
    """
    # Calculate target tokens: aim for 60% of original (40% reduction)
    target_tokens = int(original_tokens * 0.60)

    # Add 20% headroom to max_output_tokens to avoid mid-generation cutoff
    # This ensures the model has space to complete the JSON properly
    max_output = int(target_tokens * 1.2)

    # Serialize payload to JSON for LLM input
    try:
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        context.record_event(
            "mcp.summarizer.serialization_error",
            {"error": str(e), "type": payload_type}
        )
        raise ValueError(f"Cannot serialize payload for summarization: {e}")

    # Build messages for LLM
    messages = [
        {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Compress this {payload_type} JSON to ~40% smaller:\n\n{payload_json}"
        }
    ]

    # Create client and call LLM
    client = OAIClient(default_model="o4-mini")

    try:
        response = client.create_response(
            model="o4-mini",
            messages=messages,
            max_output_tokens=max_output,
            reasoning_effort="low",  # Fast inference for compression task
            text={"format": {"type": "json_object"}},  # Force JSON output
        )

        # Track tokens for this summarization call
        context.token_tracker.record_response(
            "o4-mini",
            f"observation.summarizer.{payload_type}",
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
            "mcp.summarizer.completed",
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
            "mcp.summarizer.invalid_json",
            {"error": str(e), "type": payload_type}
        )
        raise

    except Exception as e:
        context.record_event(
            "mcp.summarizer.failed",
            {"error": str(e), "type": payload_type}
        )
        raise
