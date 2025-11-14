from __future__ import annotations

from mcp_agent.planner.budget import Budget
from mcp_agent.planner.context import PlannerContext
from mcp_agent.planner.discovery import perform_initial_discovery, perform_refined_discovery


def test_perform_initial_discovery_calls_search_tools_once(monkeypatch):
    context = PlannerContext(task="Send a Slack reminder", user_id="tester", budget=Budget())
    call_count = {"value": 0}
    fake_results = [
        {
            "provider": "slack",
            "tool": "SLACK_SEND_MESSAGE",
            "available": True,
            "short_description": "Post a message",
        }
    ]

    def fake_registry_version(user_id=None):
        return 1

    def fake_search_tools(*, query, detail_level, limit, user_id):
        call_count["value"] += 1
        assert query == context.task
        assert detail_level == "summary"
        assert limit == 5
        assert user_id == context.user_id
        return fake_results

    monkeypatch.setattr("mcp_agent.planner.discovery.registry_version", fake_registry_version)
    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", fake_search_tools)

    results_first = perform_initial_discovery(context, limit=5)
    assert call_count["value"] == 1
    assert results_first == fake_results
    assert context.search_results == fake_results
    assert context.discovery_completed is True

    results_second = perform_initial_discovery(context, limit=5)
    assert call_count["value"] == 1, "Discovery should not re-run once completed."
    assert results_second == fake_results


def test_discovery_refreshes_when_registry_version_changes(monkeypatch):
    context = PlannerContext(task="Send a Slack reminder", user_id="tester", budget=Budget())
    search_calls = []

    versions = {"value": 1}

    def fake_registry_version(user_id=None):
        return versions["value"]

    def fake_search_tools(*, query, detail_level, limit, user_id):
        search_calls.append(versions["value"])
        return [
            {
                "provider": "slack",
                "tool": f"TOOL_{versions['value']}",
                "available": True,
                "short_description": "desc",
                "score": versions["value"],
            }
        ]

    monkeypatch.setattr("mcp_agent.planner.discovery.registry_version", fake_registry_version)
    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", fake_search_tools)

    perform_initial_discovery(context, limit=5)
    assert context.search_results[0]["tool"] == "TOOL_1"

    versions["value"] = 2
    perform_initial_discovery(context, limit=5)
    assert context.search_results[0]["tool"] == "TOOL_2"
    assert search_calls == [1, 2]


def test_refined_discovery_appends_and_deduplicates(monkeypatch):
    context = PlannerContext(task="demo", user_id="tester", budget=Budget())

    def fake_registry_version(user_id=None):
        return 1

    def fake_search_tools(*, query, detail_level, limit, user_id):
        return [
            {
                "provider": "gmail",
                "tool": "GMAIL_SEARCH",
                "available": True,
                "short_description": f"{query}",
                "score": len(query),
            }
        ]

    monkeypatch.setattr("mcp_agent.planner.discovery.registry_version", fake_registry_version)
    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", fake_search_tools)

    perform_initial_discovery(context, limit=5)
    assert len(context.search_results) == 1

    perform_refined_discovery(context, query="gmail attachments", detail_level="full", limit=3)
    assert len(context.search_results) == 1, "Duplicate tool entries should be deduplicated."
    assert context.tool_menu[0]["short_description"] == "gmail attachments"


def test_discovery_allows_unknown_providers(monkeypatch):
    context = PlannerContext(task="notion work", user_id="tester", budget=Budget())

    def fake_registry_version(user_id=None):
        return 1

    def fake_search_tools(*, query, detail_level, limit, user_id):
        return [
            {
                "provider": "notion",
                "tool": "NOTION_QUERY",
                "available": False,
                "short_description": "Notion placeholder",
                "score": 5,
            }
        ]

    monkeypatch.setattr("mcp_agent.planner.discovery.registry_version", fake_registry_version)
    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", fake_search_tools)

    perform_initial_discovery(context, limit=5)
    assert context.search_results[0]["provider"] == "notion"
