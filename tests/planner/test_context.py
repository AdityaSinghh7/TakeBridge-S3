from __future__ import annotations

import pytest
from mcp_agent.agent.state import (
    AgentState,
    _build_minimal_signature,
    _flatten_schema_fields,
    _shallow_schema,
    _simplify_signature,
    _slim_tool_for_planner,
)
from mcp_agent.agent.budget import Budget


def make_state(task="Test task", budget: Budget | None = None) -> AgentState:
    return AgentState(task=task, user_id="tester", request_id="test", budget=budget or Budget())


def test_shallow_schema_truncates_deep_nesting():
    """Test that _shallow_schema truncates deeply nested structures."""
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
                    },
                },
            },
            "ok": {"type": "boolean"},
        },
    }

    shallow = _shallow_schema(deep_schema, max_depth=2)

    # Top level should be preserved
    assert "properties" in shallow
    assert "message" in shallow["properties"]
    assert "ok" in shallow["properties"]

    # One level deep should be preserved
    message_props = shallow["properties"]["message"]["properties"]
    assert "blocks" in message_props

    # But deeply nested properties should be truncated
    blocks_items = message_props["blocks"]["items"]
    assert "properties" in blocks_items
    # At depth 2, nested properties should be truncated to just type
    elements_props = blocks_items["properties"]["elements"]
    assert "type" in elements_props
    # Should not have full nested structure beyond max_depth
    assert "items" not in elements_props or "properties" not in elements_props.get("items", {})


def test_shallow_schema_preserves_top_level_keys():
    """Test that _shallow_schema preserves top-level structure."""
    schema = {
        "type": "object",
        "properties": {
            "messages": {"type": "array"},
            "nextPageToken": {"type": "string"},
            "resultSizeEstimate": {"type": "integer"},
        },
        "required": ["messages"],
    }

    shallow = _shallow_schema(schema)

    assert shallow["type"] == "object"
    assert "properties" in shallow
    assert "messages" in shallow["properties"]
    assert "nextPageToken" in shallow["properties"]
    assert "resultSizeEstimate" in shallow["properties"]
    assert "required" in shallow
    assert shallow["required"] == ["messages"]


def test_slim_tool_for_planner_keeps_essential_fields():
    """Test that _slim_tool_for_planner keeps essential fields."""
    full_entry = {
        "tool_id": "gmail.gmail_search",
        "provider": "gmail",
        "server": "gmail",
        "tool": "gmail_search",
        "module": "sandbox_py.servers.gmail",
        "function": "gmail_search",
        "py_module": "sandbox_py.servers.gmail",
        "py_name": "gmail_search",
        "call_signature": "gmail.gmail_search(query: str, max_results: int = 20, ...)",
        "description": "Search Gmail",
        "short_description": "Search Gmail",
        "qualified_name": "gmail.gmail_search",
        "path": "sandbox_py/servers/gmail/gmail_search.py",
        "available": True,
        "score": 5.0,
        "input_params_pretty": ["- query: str"],
        "input_params": {"required": [{"name": "query", "type": "str"}]},
        "output_schema_pretty": ["- messages: array"],
        "output_schema": {
            "type": "object",
            "properties": {"messages": {"type": "array"}},
        },
    }

    slim = _slim_tool_for_planner(full_entry)

    # Essential fields present
    assert slim["tool_id"] == "gmail.gmail_search"
    assert slim["provider"] == "gmail"
    assert slim["server"] == "gmail"
    assert slim["py_module"] == "sandbox_py.servers.gmail"
    assert slim["py_name"] == "gmail_search"
    # Call signature should be minimal (only required args)
    assert slim["call_signature"] == "gmail.gmail_search(query)"
    assert slim["description"] == "Search Gmail"
    # Should have input_params but NOT input_params_pretty
    assert "input_params" in slim
    assert "input_params_pretty" not in slim
    # Should have output_fields but NOT output_schema or output_schema_pretty
    assert "output_fields" in slim
    assert "output_schema" not in slim
    assert "output_schema_pretty" not in slim

    # Redundant fields dropped
    assert "path" not in slim
    assert "qualified_name" not in slim
    assert "short_description" not in slim
    assert "available" not in slim
    assert "score" not in slim
    assert "tool" not in slim
    assert "module" not in slim
    assert "function" not in slim


def test_slim_tool_for_planner_fallback_to_module_function():
    """Test that _slim_tool_for_planner falls back to module/function if py_* not present."""
    entry = {
        "tool_id": "gmail.gmail_search",
        "provider": "gmail",
        "server": "gmail",
        "module": "sandbox_py.servers.gmail",
        "function": "gmail_search",
        "call_signature": "gmail.gmail_search(...)",
        "description": "Search Gmail",
    }

    slim = _slim_tool_for_planner(entry)

    assert slim["py_module"] == "sandbox_py.servers.gmail"
    assert slim["py_name"] == "gmail_search"


def test_slim_tool_for_planner_flattens_output_fields():
    """Test that _slim_tool_for_planner flattens output_schema into output_fields."""
    schema = {
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "messageId": {"type": "string"},
                        "sender": {"type": "string"},
                        "subject": {"type": "string"},
                    },
                },
            },
            "nextPageToken": {"type": "string"},
            "resultSizeEstimate": {"type": "integer"},
        },
    }

    entry = {
        "tool_id": "gmail.gmail_search",
        "provider": "gmail",
        "server": "gmail",
        "call_signature": "gmail.gmail_search(...)",
        "description": "Search Gmail",
        "output_schema": schema,
    }

    slim = _slim_tool_for_planner(entry)

    assert "output_fields" in slim
    assert isinstance(slim["output_fields"], list)
    # Should have flattened fields (leaf-level only, not intermediate objects)
    output_fields = slim["output_fields"]
    assert "messages[].messageId: string" in output_fields
    assert "messages[].sender: string" in output_fields
    assert "messages[].subject: string" in output_fields
    assert "nextPageToken: string" in output_fields
    assert "resultSizeEstimate: integer" in output_fields
    # Should NOT have output_schema
    assert "output_schema" not in slim
    # Verify count
    assert len(output_fields) == 5


def test_build_planner_state_returns_slim_search_results():
    """Test that build_planner_state returns slim search_results."""
    context = make_state()

    full_entry = {
        "tool_id": "gmail.gmail_search",
        "provider": "gmail",
        "tool": "gmail_search",
        "server": "gmail",
        "py_module": "sandbox_py.servers.gmail",
        "py_name": "gmail_search",
        "call_signature": "gmail.gmail_search(...)",
        "description": "Search Gmail",
        "path": "sandbox_py/servers/gmail/gmail_search.py",
        "score": 5.0,
        "available": True,
        "output_schema": {"type": "object", "properties": {"messages": {"type": "array"}}},
    }

    context.add_search_results([full_entry])

    snapshot = context.budget_tracker.snapshot()
    state = context.build_planner_state(snapshot)

    assert "search_results" in state
    search_results = state["search_results"]
    assert len(search_results) == 1

    slim_entry = search_results[0]
    # Should have essential fields
    assert "tool_id" in slim_entry
    assert "py_module" in slim_entry
    # Should have output_fields instead of output_schema (may be empty if schema has no leaf fields)
    assert "output_fields" in slim_entry
    assert isinstance(slim_entry["output_fields"], list)
    assert "output_schema" not in slim_entry
    # Should not have redundant fields
    assert "path" not in slim_entry
    assert "score" not in slim_entry
    assert "available" not in slim_entry

    # Full descriptor should still be in context.search_results
    assert len(context.search_results) == 1
    full_still_present = context.search_results[0]
    assert "path" in full_still_present
    assert "score" in full_still_present


def test_flatten_schema_fields():
    """Test that _flatten_schema_fields produces expected flattened paths."""
    # Gmail search schema
    gmail_schema = {
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "messageId": {"type": "string"},
                        "sender": {"type": "string"},
                        "subject": {"type": "string"},
                        "preview": {
                            "type": "object",
                            "properties": {
                                "subject": {"type": "string"},
                                "body": {"type": "string"},
                            },
                        },
                    },
                },
            },
            "nextPageToken": {"type": "string"},
            "resultSizeEstimate": {"type": "integer"},
        },
    }

    fields = _flatten_schema_fields(gmail_schema)
    assert isinstance(fields, list)
    # Flatten function returns leaf-level fields only (not intermediate objects)
    assert "messages[].messageId: string" in fields
    assert "messages[].sender: string" in fields
    assert "messages[].subject: string" in fields
    assert "messages[].preview.subject: string" in fields
    assert "messages[].preview.body: string" in fields
    assert "nextPageToken: string" in fields
    assert "resultSizeEstimate: integer" in fields
    # Verify count
    assert len(fields) == 7

    # Slack search schema (nested messages structure)
    slack_schema = {
        "type": "object",
        "properties": {
            "messages": {
                "type": "object",
                "properties": {
                    "matches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "ts": {"type": "string"},
                            },
                        },
                    },
                },
            },
            "ok": {"type": "boolean"},
        },
    }

    fields = _flatten_schema_fields(slack_schema)
    # Flatten function returns leaf-level fields only (not intermediate objects)
    assert "messages.matches[].text: string" in fields
    assert "messages.matches[].ts: string" in fields
    assert "ok: boolean" in fields
    # Verify count
    assert len(fields) == 3


def test_build_minimal_signature():
    """Test that _build_minimal_signature creates signature with only required args."""
    entry1 = {
        "tool_id": "gmail.gmail_search",
        "input_params": {
            "required": [{"name": "query", "type": "str"}],
            "optional": [{"name": "max_results", "type": "int", "default": 20}],
        },
    }
    sig = _build_minimal_signature(entry1)
    assert sig == "gmail.gmail_search(query)"

    entry2 = {
        "tool_id": "gmail.gmail_send_email",
        "input_params": {
            "required": [
                {"name": "to", "type": "str"},
                {"name": "subject", "type": "str"},
                {"name": "body", "type": "str"},
            ],
            "optional": [{"name": "cc", "type": "str", "default": ""}],
        },
    }
    sig = _build_minimal_signature(entry2)
    assert sig == "gmail.gmail_send_email(to, subject, body)"

    # Test with no required args
    entry3 = {
        "tool_id": "tool.func",
        "input_params": {
            "required": [],
            "optional": [{"name": "param", "type": "int", "default": 0}],
        },
    }
    sig = _build_minimal_signature(entry3)
    assert sig == "tool.func()"

    # Test fallback when no tool_id
    entry4 = {
        "provider": "gmail",
        "py_name": "gmail_search",
        "input_params": {"required": [{"name": "query", "type": "str"}]},
    }
    sig = _build_minimal_signature(entry4)
    assert sig == "gmail.gmail_search(query)"

    # Test fallback when no input_params
    entry5 = {"tool_id": "gmail.gmail_search"}
    sig = _build_minimal_signature(entry5)
    assert sig == "gmail.gmail_search()"


def test_simplify_signature():
    """Test that _simplify_signature removes type annotations and normalizes spaces."""
    sig1 = "gmail.gmail_search(query: str, max_results: int = 20, ...)"
    simplified = _simplify_signature(sig1)
    assert simplified == "gmail.gmail_search(query, max_results=20, ...)"

    sig2 = "slack.slack_post_message(channel: str, text: str = '', markdown_text: str = '')"
    simplified = _simplify_signature(sig2)
    assert simplified == "slack.slack_post_message(channel, text='', markdown_text='')"

    sig3 = "tool.func(param: int)"
    simplified = _simplify_signature(sig3)
    assert simplified == "tool.func(param)"

    # Test with spaces around = (common in formatted signatures)
    sig4 = "gmail.gmail_search(query: str, max_results: int = 20, label_ids: Any | None = None)"
    simplified = _simplify_signature(sig4)
    assert simplified == "gmail.gmail_search(query, max_results=20, label_ids=None)"
    # Verify no spaces around =
    assert "= " not in simplified
    assert " =" not in simplified

    # Empty or None should return as-is
    assert _simplify_signature("") == ""
    assert _simplify_signature(None) is None
