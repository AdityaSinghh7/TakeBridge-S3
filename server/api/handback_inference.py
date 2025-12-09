"""
Handback inference helper.

Calls OpenAI o4-mini to infer what the human did between the handback screenshot
and the current screenshot, and whether the agent's request was fulfilled.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from shared.oai_client import OAIClient, extract_assistant_text

logger = logging.getLogger(__name__)

INFERENCE_SYSTEM_PROMPT = """You are an assistant that analyzes screenshots to determine what actions a human user performed.

You will be given:
1. The agent's original request to the human (what the agent needed help with)
2. A "before" screenshot taken when the agent requested human intervention
3. An "after" screenshot taken after the human had time to act

Your task is to:
1. Carefully compare the two screenshots
2. Identify what changed between them
3. Determine if the human fulfilled the agent's request

Respond in JSON format with the following structure:
{
    "changes_observed": "A detailed description of what changed between the screenshots",
    "request_fulfilled": true or false,
    "confidence": "high", "medium", or "low",
    "details": "Additional context about the changes and whether they address the agent's request"
}

Be specific about UI changes, login states, form submissions, navigation, or any other visible modifications.
If the screenshots appear identical, note that no visible changes occurred."""


def infer_human_action(
    request: str,
    before_screenshot_b64: str,
    after_screenshot_b64: str,
) -> Dict[str, Any]:
    """
    Call o4-mini to infer what the human did between screenshots.

    Args:
        request: The original request the agent made to the human
        before_screenshot_b64: Base64-encoded screenshot from handback time
        after_screenshot_b64: Base64-encoded screenshot of current state

    Returns:
        Dict with:
            - changes_observed: str - description of what changed
            - request_fulfilled: bool - whether the request appears fulfilled
            - confidence: str - "high", "medium", or "low"
            - details: str - additional context
    """
    client = OAIClient(
        default_model="o4-mini",
        default_reasoning_effort="medium",
        max_retries=2,
    )

    messages = [
        {
            "role": "system",
            "content": INFERENCE_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Agent's request to human: {request}",
                },
                {
                    "type": "text",
                    "text": "BEFORE screenshot (when agent requested human help):",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{before_screenshot_b64}",
                    },
                },
                {
                    "type": "text",
                    "text": "AFTER screenshot (current state after human action):",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{after_screenshot_b64}",
                    },
                },
                {
                    "type": "text",
                    "text": "Please analyze these screenshots and respond in the specified JSON format.",
                },
            ],
        },
    ]

    try:
        response = client.create_response(
            model="o4-mini",
            messages=messages,
            max_output_tokens=2000,
            reasoning_effort="medium",
        )

        text = extract_assistant_text(response)
        logger.info("Handback inference raw response: %s", text[:500])

        # Parse the JSON response
        # Handle potential markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)

        # Validate and normalize the response
        return {
            "changes_observed": str(result.get("changes_observed", "Unable to determine changes")),
            "request_fulfilled": bool(result.get("request_fulfilled", False)),
            "confidence": str(result.get("confidence", "low")).lower(),
            "details": str(result.get("details", "")),
        }

    except json.JSONDecodeError as e:
        logger.error("Failed to parse handback inference JSON: %s", e)
        return {
            "changes_observed": "Unable to parse model response",
            "request_fulfilled": False,
            "confidence": "low",
            "details": f"JSON parse error: {str(e)}",
        }
    except Exception as e:
        logger.error("Handback inference failed: %s", e)
        return {
            "changes_observed": "Inference failed",
            "request_fulfilled": False,
            "confidence": "low",
            "details": f"Error: {str(e)}",
        }


def format_inference_for_context(inference: Dict[str, Any], request: str) -> str:
    """
    Format the inference result as a string for inclusion in agent context.

    Args:
        inference: The inference result dict
        request: The original handback request

    Returns:
        Formatted string for agent context
    """
    fulfilled_str = "YES" if inference.get("request_fulfilled") else "NO"
    confidence = inference.get("confidence", "unknown")
    changes = inference.get("changes_observed", "No changes observed")
    details = inference.get("details", "")

    result = f"""The agent previously requested human intervention: "{request}"

Human Action Analysis:
- Request Fulfilled: {fulfilled_str} (confidence: {confidence})
- Changes Observed: {changes}"""

    if details:
        result += f"\n- Additional Details: {details}"

    return result


__all__ = ["infer_human_action", "format_inference_for_context"]

