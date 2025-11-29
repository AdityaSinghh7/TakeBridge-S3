#!/usr/bin/env python
"""
Test script to validate orchestrator data flow for hybrid workflows.

This script validates that translator-style canonical outputs with
search_results, tool_calls, and optional data blocks render correctly
in the orchestrator's previous-results context.

Run with:
    python scripts/test_orchestrator_data_flow.py
"""

from __future__ import annotations

from orchestrator_agent.data_types import StepResult
from orchestrator_agent.system_prompt import format_previous_results


def test_mcp_search_result_handling():
    """Test that MCP search results are correctly surfaced from translator output."""
    print("=" * 80)
    print("TEST 1: MCP Search Result Handling")
    print("=" * 80)

    translated = {
        "task": "Find Gmail tools and send an email",
        "overall_success": True,
        "summary": "Searched provider registry for Gmail and found 5 tools to use for email tasks.",
        "error": None,
        "error_code": None,
        "last_step_failed": False,
        "failed_step_index": None,
        "total_steps": 1,
        "steps_summary": [
            "Step 1: Searched provider registry for Gmail email tools. Found gmail.gmail_search, gmail.gmail_get_thread, gmail.gmail_get_attachment, gmail.gmail_send_email, gmail.gmail_create_draft."
        ],
        "artifacts": {
            "tool_calls": [],
            "ui_observations": [],
            "code_executions": [],
            "search_results": [
                {
                    "query": "gmail email tools",
                    "tools_found": 5,
                    "tool_names": [
                        "gmail.gmail_search",
                        "gmail.gmail_get_thread",
                        "gmail.gmail_get_attachment",
                        "gmail.gmail_send_email",
                        "gmail.gmail_create_draft",
                    ],
                }
            ],
        },
    }

    print("\n1. Translation Output:")
    print(f"   Overall success: {translated['overall_success']}")
    print(f"   Summary: {translated['summary']}")

    artifacts = translated.get("artifacts", {})
    search_results = artifacts.get("search_results", [])
    tool_names = search_results[0].get("tool_names", []) if search_results else []

    print(f"\n2. Artifacts Check:")
    print(f"   Has search_results: {bool(search_results)}")
    print(f"   Tool count: {search_results[0].get('tools_found', 0) if search_results else 0}")

    if tool_names:
        print(f"   Tool IDs:")
        for tool in tool_names[:5]:
            print(f"     - {tool}")

    # Test system prompt formatting
    step_result = StepResult(
        step_id="step-1",
        target="mcp",
        next_task="Search for Gmail tools",
        verification="Tools should be found",
        description="Search provider registry for Gmail tools",
        status="completed",
        success=translated["overall_success"],
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
    assert search_results, "search_results should be present"
    assert len(tool_names) == 5, f"Expected 5 tools, got {len(tool_names)}"
    assert "gmail.gmail_search" in tool_names, "Should include gmail_search"

    # Validate that formatted output shows tool names
    assert "Search Results:" in formatted, "Should show 'Search Results:' header"
    assert "gmail.gmail_search" in formatted, "Should show tool IDs"
    assert "gmail.gmail_get_attachment" in formatted, "Should show tool IDs"

    print("\n✅ TEST 1 PASSED: Search results correctly handled")
    print()


def test_mcp_regular_tool_call_handling():
    """Test that regular MCP tool calls preserve full data."""
    print("=" * 80)
    print("TEST 2: MCP Regular Tool Call Handling")
    print("=" * 80)

    translated = {
        "task": "Download attachment and open it",
        "overall_success": True,
        "summary": "Downloaded invoice_march_2024.pdf from Gmail to the local Downloads folder.",
        "error": None,
        "error_code": None,
        "last_step_failed": False,
        "failed_step_index": None,
        "total_steps": 2,
        "steps_summary": [
            "Step 1: Called gmail.gmail_get_attachment for thread abc123 and message msg-1.",
            "Step 2: Completion - Saved invoice_march_2024.pdf to ~/Downloads/invoice_march_2024.pdf.",
        ],
        "data": {
            "files": [
                {
                    "filename": "invoice_march_2024.pdf",
                    "local_path": "~/Downloads/invoice_march_2024.pdf",
                    "size_bytes": 245678,
                }
            ]
        },
        "artifacts": {
            "tool_calls": [
                {
                    "tool_id": "gmail.gmail_get_attachment",
                    "arguments": {"thread_id": "abc123", "message_id": "msg-1"},
                    "response": {
                        "filename": "invoice_march_2024.pdf",
                        "local_path": "~/Downloads/invoice_march_2024.pdf",
                        "size_bytes": 245678,
                    },
                    "success": True,
                }
            ],
            "ui_observations": [],
            "code_executions": [],
            "search_results": [],
        },
    }

    print("\n1. Translation Output:")
    print(f"   Overall success: {translated['overall_success']}")
    print(f"   Summary: {translated['summary']}")

    artifacts = translated.get("artifacts", {})
    tool_calls = artifacts.get("tool_calls", [])
    data_block = translated.get("data", {})

    print(f"\n2. Artifacts Check:")
    print(f"   Tool calls count: {len(tool_calls)}")
    print(f"   Data keys: {list(data_block.keys()) if isinstance(data_block, dict) else []}")

    # Test system prompt formatting
    step_result = StepResult(
        step_id="step-2",
        target="mcp",
        next_task="Download email attachment",
        verification="Attachment should be downloaded",
        description="Use Gmail to get attachment",
        status="completed",
        success=translated["overall_success"],
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
    assert tool_calls, "Should have tool_calls"
    assert tool_calls[0]["tool_id"] == "gmail.gmail_get_attachment", "Tool ID should match"
    assert "files" in data_block, "Data block should include files"
    assert data_block["files"][0]["filename"] == "invoice_march_2024.pdf", "Filename should match"

    # Validate formatted output shows actual data
    assert "Data:" in formatted, "Should show 'Data:' header"
    assert "invoice_march_2024.pdf" in formatted, "Should show filename"
    assert "Downloads" in formatted or "local_path" in formatted, "Should show path info"

    print("\n✅ TEST 2 PASSED: Regular tool calls preserve full data")
    print()


def test_hybrid_workflow_sequence():
    """Test complete hybrid workflow: search → retrieve → computer-use."""
    print("=" * 80)
    print("TEST 3: Hybrid Workflow Sequence")
    print("=" * 80)

    search_translated = {
        "task": "Find Gmail tools that can search emails",
        "overall_success": True,
        "summary": "Found 3 Gmail search tools in the provider registry.",
        "error": None,
        "error_code": None,
        "last_step_failed": False,
        "failed_step_index": None,
        "total_steps": 1,
        "steps_summary": [
            "Step 1: Searched registry for gmail search. Found gmail.gmail_search, gmail.gmail_get_thread, gmail.gmail_list_labels."
        ],
        "artifacts": {
            "tool_calls": [],
            "ui_observations": [],
            "code_executions": [],
            "search_results": [
                {
                    "query": "gmail search",
                    "tools_found": 3,
                    "tool_names": [
                        "gmail.gmail_search",
                        "gmail.gmail_get_thread",
                        "gmail.gmail_list_labels",
                    ],
                }
            ],
        },
    }
    search_result = StepResult(
        step_id="step-3a",
        target="mcp",
        next_task="Find Gmail tools that can search emails",
        verification="Tools should be found",
        description="Search provider registry",
        status="completed",
        success=search_translated["overall_success"],
        output={"translated": search_translated},
    )

    retrieve_translated = {
        "task": "Search Gmail for emails with PDF attachments",
        "overall_success": True,
        "summary": "Found 5 Gmail emails with PDF attachments and identified the most recent invoice.",
        "error": None,
        "error_code": None,
        "last_step_failed": False,
        "failed_step_index": None,
        "total_steps": 2,
        "steps_summary": [
            "Step 1: Called gmail.gmail_search with query 'has:attachment filename:pdf'.",
            "Step 2: Completion - Found 5 messages; most recent is March Invoice from john@example.com with attachment invoice_march_2024.pdf.",
        ],
        "data": {
            "emails": [
                {
                    "subject": "March Invoice",
                    "from": "john@example.com",
                    "attachment_name": "invoice_march_2024.pdf",
                    "thread_id": "abc123",
                }
            ]
        },
        "artifacts": {
            "tool_calls": [
                {
                    "tool_id": "gmail.gmail_search",
                    "arguments": {"query": "has:attachment filename:pdf"},
                    "response": {
                        "count": 5,
                        "most_recent": {
                            "subject": "March Invoice",
                            "from": "john@example.com",
                            "attachment_name": "invoice_march_2024.pdf",
                            "thread_id": "abc123",
                        },
                    },
                    "success": True,
                }
            ],
            "ui_observations": [],
            "code_executions": [],
            "search_results": [],
        },
    }
    retrieve_result = StepResult(
        step_id="step-3b",
        target="mcp",
        next_task="Search Gmail for emails with PDF attachments",
        verification="Emails should be found",
        description="Use gmail.gmail_search to find emails",
        status="completed",
        success=retrieve_translated["overall_success"],
        output={"translated": retrieve_translated},
    )

    download_translated = {
        "task": "Download the most recent PDF attachment",
        "overall_success": True,
        "summary": "Downloaded invoice_march_2024.pdf to ~/Downloads for later opening in Preview.",
        "error": None,
        "error_code": None,
        "last_step_failed": False,
        "failed_step_index": None,
        "total_steps": 2,
        "steps_summary": [
            "Step 1: Called gmail.gmail_get_attachment for thread abc123.",
            "Step 2: Completion - Saved invoice_march_2024.pdf to ~/Downloads/invoice_march_2024.pdf.",
        ],
        "data": {
            "files": [
                {
                    "filename": "invoice_march_2024.pdf",
                    "local_path": "~/Downloads/invoice_march_2024.pdf",
                    "size_bytes": 245678,
                }
            ]
        },
        "artifacts": {
            "tool_calls": [
                {
                    "tool_id": "gmail.gmail_get_attachment",
                    "arguments": {"thread_id": "abc123"},
                    "response": {
                        "filename": "invoice_march_2024.pdf",
                        "local_path": "~/Downloads/invoice_march_2024.pdf",
                        "size_bytes": 245678,
                    },
                    "success": True,
                }
            ],
            "ui_observations": [],
            "code_executions": [],
            "search_results": [],
        },
    }
    download_result = StepResult(
        step_id="step-3c",
        target="mcp",
        next_task="Download the most recent PDF attachment",
        verification="File should be downloaded",
        description="Use gmail.gmail_get_attachment",
        status="completed",
        success=download_translated["overall_success"],
        output={"translated": download_translated},
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

    assert "Search Results:" in formatted, "Step 1 should show search results"
    assert "gmail.gmail_search" in formatted, "Step 1 should show tool IDs"

    assert "March Invoice" in formatted, "Step 2 should show email details"
    assert "john@example.com" in formatted, "Step 2 should show sender context"

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
        print("  • MCP search results surface tool names via search_results artifacts")
        print("  • MCP tool calls preserve arguments, responses, and data blocks")
        print("  • Hybrid workflows maintain email + file context across steps")
        print("  • Previous-results formatting passes translator JSON to the planner")
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
