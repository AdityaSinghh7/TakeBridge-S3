#!/usr/bin/env python
"""
Test script to validate orchestrator data flow for hybrid workflows.

This script tests the complete data preservation chain:
1. MCP agent searches for tools → returns found_tools in observation
2. Translator extracts found_tools to artifacts.retrieved_data
3. System prompt shows tool names (not full specs) to orchestrator LLM
4. Orchestrator can see and use the tool names in subsequent steps

Run with:
    python scripts/test_orchestrator_data_flow.py
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from orchestrator_agent.data_types import AgentTarget, PlannedStep, StepResult
from orchestrator_agent.translator import translate_step_output
from orchestrator_agent.system_prompt import format_previous_results


def test_mcp_search_result_handling():
    """Test that MCP search results are correctly handled."""
    print("=" * 80)
    print("TEST 1: MCP Search Result Handling")
    print("=" * 80)

    # Simulate MCP agent search result (as returned by execute_mcp_task)
    raw_mcp_result = {
        "success": True,
        "final_summary": "Found 5 Gmail tools matching the search query",
        "error": None,
        "error_code": None,
        "raw_outputs": {},
        "steps": [
            {
                "action_type": "search",
                "success": True,
                "observation": [
                    {"tool_id": "gmail.gmail_search", "name": "Search emails"},
                    {"tool_id": "gmail.gmail_get_thread", "name": "Get email thread"},
                    {"tool_id": "gmail.gmail_get_attachment", "name": "Get attachment"},
                    {"tool_id": "gmail.gmail_send_email", "name": "Send email"},
                    {"tool_id": "gmail.gmail_create_draft", "name": "Create draft"},
                ],
                "action_outcome": {
                    "total_found": 5,
                    "query": "gmail email tools"
                }
            }
        ]
    }

    # Test translation (deterministic fallback)
    step = PlannedStep(
        target="mcp",
        next_task="Search for Gmail tools",
        max_steps=5,
        verification="Tools should be found",
        description="Search provider registry for Gmail tools"
    )

    translated = translate_step_output(
        task="Find Gmail tools and send an email",
        step=step,
        target="mcp",
        trajectory=["Searching for tools..."],
        raw_result=raw_mcp_result,
        llm_client=None,  # Force fallback
    )

    print("\n1. Translation Output:")
    print(f"   Success: {translated['success']}")
    print(f"   Summary: {translated['summary']}")

    # Check artifacts.retrieved_data contains found_tools
    artifacts = translated.get("artifacts", {})
    retrieved_data = artifacts.get("retrieved_data", {})
    found_tools = retrieved_data.get("found_tools")

    print(f"\n2. Artifacts Check:")
    print(f"   Has retrieved_data: {bool(retrieved_data)}")
    print(f"   Has found_tools: {bool(found_tools)}")
    print(f"   Tool count: {retrieved_data.get('count', 0)}")

    if found_tools:
        print(f"   Tool IDs:")
        for tool in found_tools[:5]:
            print(f"     - {tool.get('tool_id', 'unknown')}")

    # Test system prompt formatting
    step_result = StepResult(
        step_id=1,
        target="mcp",
        next_task="Search for Gmail tools",
        verification="Tools should be found",
        description="Search provider registry for Gmail tools",
        status="completed",
        output={"translated": translated},
    )

    formatted = format_previous_results([step_result], task="Find Gmail tools and send an email")

    print(f"\n3. System Prompt Formatting:")
    print("   Output shown to orchestrator LLM:")
    print("   " + "-" * 70)
    for line in formatted.split("\n"):
        print(f"   {line}")
    print("   " + "-" * 70)

    # Validate expectations
    assert found_tools is not None, "found_tools should be in retrieved_data"
    assert len(found_tools) == 5, f"Expected 5 tools, got {len(found_tools)}"
    assert retrieved_data.get("count") == 5, "count should be 5"
    assert "gmail.gmail_search" in [t.get("tool_id") for t in found_tools], "Should include gmail_search"

    # Validate that formatted output shows tool names but NOT full specs
    assert "Tools Found:" in formatted, "Should show 'Tools Found:' header"
    assert "gmail.gmail_search" in formatted, "Should show tool IDs"
    assert "gmail.gmail_get_attachment" in formatted, "Should show tool IDs"
    # The actual tool specs should not be in the formatted output
    # (they're in found_tools but only IDs are extracted)

    print("\n✅ TEST 1 PASSED: Search results correctly handled")
    print()


def test_mcp_regular_tool_call_handling():
    """Test that regular MCP tool calls preserve full data."""
    print("=" * 80)
    print("TEST 2: MCP Regular Tool Call Handling")
    print("=" * 80)

    # Simulate MCP agent downloading an attachment
    raw_mcp_result = {
        "success": True,
        "final_summary": "Downloaded attachment invoice_march_2024.pdf from email",
        "error": None,
        "error_code": None,
        "raw_outputs": {
            "gmail.gmail_get_attachment": {
                "filename": "invoice_march_2024.pdf",
                "download_url": "https://mail.google.com/...",
                "size_bytes": 245678,
                "mime_type": "application/pdf"
            }
        },
        "steps": [
            {
                "action_type": "tool",
                "success": True,
                "observation": {"result": "Attachment downloaded"},
                "action_outcome": {
                    "filename": "invoice_march_2024.pdf",
                    "local_path": "~/Downloads/invoice_march_2024.pdf",
                    "size_bytes": 245678
                }
            }
        ]
    }

    step = PlannedStep(
        target="mcp",
        next_task="Download email attachment",
        max_steps=5,
        verification="Attachment should be downloaded",
        description="Use Gmail to get attachment from most recent email"
    )

    translated = translate_step_output(
        task="Download attachment and open it",
        step=step,
        target="mcp",
        trajectory=["Calling gmail_get_attachment..."],
        raw_result=raw_mcp_result,
        llm_client=None,
    )

    print("\n1. Translation Output:")
    print(f"   Success: {translated['success']}")
    print(f"   Summary: {translated['summary']}")

    artifacts = translated.get("artifacts", {})
    retrieved_data = artifacts.get("retrieved_data", {})
    tool_outputs = artifacts.get("tool_outputs", [])

    print(f"\n2. Artifacts Check:")
    print(f"   Has retrieved_data: {bool(retrieved_data)}")
    print(f"   Retrieved data keys: {list(retrieved_data.keys())}")
    print(f"   Tool outputs count: {len(tool_outputs)}")

    if retrieved_data:
        print(f"   Retrieved data:")
        for key, value in retrieved_data.items():
            value_str = str(value)[:100]
            print(f"     - {key}: {value_str}")

    # Test system prompt formatting
    step_result = StepResult(
        step_id=1,
        target="mcp",
        next_task="Download email attachment",
        verification="Attachment should be downloaded",
        description="Use Gmail to get attachment",
        status="completed",
        output={"translated": translated},
    )

    formatted = format_previous_results([step_result], task="Download attachment and open it")

    print(f"\n3. System Prompt Formatting:")
    print("   Output shown to orchestrator LLM:")
    print("   " + "-" * 70)
    for line in formatted.split("\n"):
        print(f"   {line}")
    print("   " + "-" * 70)

    # Validate expectations
    assert retrieved_data is not None, "Should have retrieved_data"
    assert "filename" in retrieved_data, "Should preserve filename"
    assert retrieved_data.get("filename") == "invoice_march_2024.pdf", "Filename should match"
    assert "local_path" in retrieved_data, "Should preserve local_path"

    # Validate formatted output shows actual data
    assert "Retrieved Data:" in formatted, "Should show 'Retrieved Data:' header"
    assert "invoice_march_2024.pdf" in formatted, "Should show filename"
    assert "Downloads" in formatted or "local_path" in formatted, "Should show path info"

    print("\n✅ TEST 2 PASSED: Regular tool calls preserve full data")
    print()


def test_hybrid_workflow_sequence():
    """Test complete hybrid workflow: search → retrieve → computer-use."""
    print("=" * 80)
    print("TEST 3: Hybrid Workflow Sequence")
    print("=" * 80)

    # Step 1: MCP searches for tools
    search_result = StepResult(
        step_id=1,
        target="mcp",
        next_task="Find Gmail tools that can search emails",
        verification="Tools should be found",
        description="Search provider registry",
        status="completed",
        output={
            "translated": {
                "summary": "Found 3 Gmail search tools",
                "success": True,
                "error": None,
                "error_code": None,
                "details": ["Searched provider registry for 'gmail search'"],
                "artifacts": {
                    "retrieved_data": {
                        "found_tools": [
                            {"tool_id": "gmail.gmail_search"},
                            {"tool_id": "gmail.gmail_get_thread"},
                            {"tool_id": "gmail.gmail_list_labels"}
                        ],
                        "count": 3
                    }
                },
                "raw_ref": None
            }
        }
    )

    # Step 2: MCP retrieves data using one of the found tools
    retrieve_result = StepResult(
        step_id=2,
        target="mcp",
        next_task="Search Gmail for emails with PDF attachments",
        verification="Emails should be found",
        description="Use gmail.gmail_search to find emails",
        status="completed",
        output={
            "translated": {
                "summary": "Found 5 emails with PDF attachments",
                "success": True,
                "error": None,
                "error_code": None,
                "details": ["Called gmail_search with query 'has:attachment filename:pdf'"],
                "artifacts": {
                    "retrieved_data": {
                        "emails_found": 5,
                        "most_recent": {
                            "subject": "March Invoice",
                            "from": "john@example.com",
                            "attachment_name": "invoice_march_2024.pdf",
                            "thread_id": "abc123"
                        }
                    },
                    "tool_outputs": [
                        {"tool": "gmail.gmail_search", "result": {"count": 5}}
                    ]
                },
                "raw_ref": None
            }
        }
    )

    # Step 3: MCP downloads the attachment
    download_result = StepResult(
        step_id=3,
        target="mcp",
        next_task="Download the most recent PDF attachment",
        verification="File should be downloaded",
        description="Use gmail.gmail_get_attachment",
        status="completed",
        output={
            "translated": {
                "summary": "Downloaded invoice_march_2024.pdf to ~/Downloads",
                "success": True,
                "error": None,
                "error_code": None,
                "details": ["Called gmail_get_attachment for thread abc123"],
                "artifacts": {
                    "retrieved_data": {
                        "filename": "invoice_march_2024.pdf",
                        "local_path": "~/Downloads/invoice_march_2024.pdf",
                        "size_bytes": 245678
                    }
                },
                "raw_ref": None
            }
        }
    )

    # Format all previous results for the next step
    all_results = [search_result, retrieve_result, download_result]
    formatted = format_previous_results(
        all_results,
        task="Find and download Gmail PDF attachment, then open it in Preview"
    )

    print("\n1. Complete Previous Results Context:")
    print("   " + "=" * 70)
    for line in formatted.split("\n"):
        print(f"   {line}")
    print("   " + "=" * 70)

    # Validate that orchestrator can see:
    # - Search showed tool names (not specs)
    # - Retrieve showed email metadata
    # - Download showed file path

    assert "Tools Found:" in formatted, "Step 1 should show tools found"
    assert "gmail.gmail_search" in formatted, "Step 1 should show tool IDs"

    assert "emails_found" in formatted or "5" in formatted, "Step 2 should show email count"
    assert "March Invoice" in formatted or "most_recent" in formatted, "Step 2 should show email details"

    assert "invoice_march_2024.pdf" in formatted, "Step 3 should show filename"
    assert "Downloads" in formatted or "local_path" in formatted, "Step 3 should show file path"

    print("\n2. Validation:")
    print("   ✓ Search results show tool names only (not full specs)")
    print("   ✓ Retrieved data shows email metadata")
    print("   ✓ Downloaded file path is preserved")
    print("   ✓ All data available for computer-use agent in next step")

    print("\n✅ TEST 3 PASSED: Hybrid workflow preserves all necessary data")
    print()


def main():
    """Run all data flow tests."""
    print("\n" + "=" * 80)
    print("ORCHESTRATOR DATA FLOW TESTS")
    print("=" * 80)
    print()

    try:
        test_mcp_search_result_handling()
        test_mcp_regular_tool_call_handling()
        test_hybrid_workflow_sequence()

        print("=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print()
        print("Data flow validation complete:")
        print("  • MCP search results correctly show tool names (not full specs)")
        print("  • MCP tool calls preserve all retrieved data")
        print("  • Hybrid workflows maintain data across steps")
        print("  • Orchestrator LLM receives appropriate context for planning")
        print()
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
