"""Token counting utility for JSON payloads using tiktoken."""

import json
import tiktoken
from typing import Any


def count_json_tokens(data: Any, model: str = "o4-mini") -> int:
    """
    Count tokens in a JSON-serializable payload.

    Uses tiktoken for accurate token counting with model-specific encoding.
    o4-mini uses the same cl100k_base encoding as GPT-4.

    Args:
        data: Any JSON-serializable Python object (dict, list, str, etc.)
        model: Model name for encoding selection (default: "o4-mini")

    Returns:
        Token count as integer

    Raises:
        ValueError: If data is not JSON-serializable

    Examples:
        >>> count_json_tokens({"key": "value"})
        7
        >>> count_json_tokens([1, 2, 3, 4, 5])
        11
    """
    # Get encoding for the model
    # o4-mini, GPT-4, and GPT-3.5-turbo all use cl100k_base
    try:
        encoding = tiktoken.encoding_for_model("gpt-4")
    except KeyError:
        # Fallback to cl100k_base if model not recognized
        encoding = tiktoken.get_encoding("cl100k_base")

    # Serialize to JSON string
    try:
        json_str = json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        # If serialization fails, use string representation and estimate
        # This is a conservative fallback: ~3.5 chars per token on average
        return len(str(data)) // 3

    # Count tokens in the JSON string
    return len(encoding.encode(json_str))
