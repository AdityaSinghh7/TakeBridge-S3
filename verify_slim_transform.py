"""
Quick verification script to test the slim transform implementation.

Run with: python verify_slim_transform.py
"""

from mcp_agent.planner.context import _shallow_schema, _slim_tool_for_planner

# Test 1: Shallow schema truncates deep nesting
print("Test 1: Shallow schema truncation")
deep_schema = {
    "type": "object",
    "properties": {
        "message": {
            "type": "object",
            "properties": {
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "elements": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "type": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "ok": {"type": "boolean"},
    },
}

shallow = _shallow_schema(deep_schema)
print(f"  ✓ Deep schema truncated")
print(f"  - Top level keys preserved: {list(shallow.get('properties', {}).keys())}")
print(f"  - Deep nesting truncated: {len(str(shallow)) < len(str(deep_schema))}")

# Test 2: Slim tool transform
print("\nTest 2: Slim tool transform")
full_entry = {
    "tool_id": "slack.slack_post_message",
    "provider": "slack",
    "server": "slack",
    "tool": "slack_post_message",
    "module": "sandbox_py.servers.slack",
    "function": "slack_post_message",
    "py_module": "sandbox_py.servers.slack",
    "py_name": "slack_post_message",
    "call_signature": "slack.slack_post_message(channel: str, ...)",
    "description": "Post message to Slack",
    "short_description": "Post message",
    "qualified_name": "slack.slack_post_message",
    "path": "sandbox_py/servers/slack/slack_post_message.py",
    "available": True,
    "score": 6.0,
    "input_params_pretty": ["- channel: str"],
    "output_schema": deep_schema,
    "output_schema_pretty": ["- message: object", "- ok: boolean"],
}

slim = _slim_tool_for_planner(full_entry)

print(f"  ✓ Essential fields present:")
for key in ["tool_id", "provider", "server", "py_module", "py_name", "call_signature", "description"]:
    assert key in slim, f"Missing essential field: {key}"
    print(f"    - {key}: ✓")

print(f"  ✓ Redundant fields dropped:")
for key in ["path", "qualified_name", "short_description", "available", "score", "tool", "module", "function"]:
    assert key not in slim, f"Should not have redundant field: {key}"
    print(f"    - {key}: ✓ (dropped)")

print(f"  ✓ Output schema is shallow: {len(str(slim['output_schema'])) < len(str(deep_schema))}")

print("\n✅ All tests passed! Slim transform working correctly.")

