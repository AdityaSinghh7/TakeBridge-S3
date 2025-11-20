from __future__ import annotations

from mcp_agent.agent.budget import Budget
from mcp_agent.agent.state import AgentState


def make_state(task: str = "demo") -> AgentState:
    return AgentState(task=task, user_id="tester", request_id="test", budget=Budget())


def test_merge_search_results_appends_once():
    state = make_state()
    results = [
        {"provider": "slack", "tool": "send", "available": True, "score": 10},
    ]
    state.merge_search_results(results)
    assert state.search_results == results
    assert state.discovery_completed is True

    # second call with same data should not duplicate entries
    state.merge_search_results(results)
    assert len(state.search_results) == 1


def test_merge_search_results_replace_on_refresh():
    state = make_state()
    state.merge_search_results([
        {"provider": "slack", "tool": "old", "available": True, "score": 1},
    ])
    state.merge_search_results([
        {"provider": "slack", "tool": "new", "available": True, "score": 5},
    ], replace=True)
    assert len(state.search_results) == 1
    assert state.search_results[0]["tool"] == "new"


def test_merge_search_results_keeps_highest_score_duplicate():
    state = make_state()
    state.merge_search_results(
        [{"provider": "gmail", "tool": "search", "available": True, "score": 1}]
    )
    state.merge_search_results(
        [{"provider": "gmail", "tool": "search", "available": True, "score": 5}]
    )
    assert state.search_results[0]["score"] == 5


def test_merge_search_results_allows_unknown_provider():
    state = make_state("notion work")
    results = [
        {"provider": "notion", "tool": "query", "available": True, "score": 3},
    ]
    state.merge_search_results(results)
    assert state.search_results[0]["provider"] == "notion"
    assert any(item["qualified_name"].startswith("notion") for item in state.tool_menu)
