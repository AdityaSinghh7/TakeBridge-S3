from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from mcp_agent.planner import Budget, execute_mcp_task


def _run_simple_task(user_id: str, task: str) -> dict:
    return execute_mcp_task(task, user_id=user_id, budget=Budget(max_steps=2))


def test_concurrent_tasks_different_users():
    users = [f"user-{idx}" for idx in range(4)]
    tasks = [f"Task {idx}" for idx in range(4)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(_run_simple_task, user, task)
            for user, task in zip(users, tasks)
        ]
        results = [f.result() for f in futures]

    assert all(isinstance(result, dict) for result in results)
    # Ensure each result has its own logs and raw_outputs; we don't assert on
    # contents here, just shape and isolation.
    for result in results:
        assert "logs" in result
        assert "raw_outputs" in result
        # user_id should be echoed in the result for debugging multi-tenant flows.
        assert result.get("user_id")


def test_concurrent_tasks_same_user_distinct_run_ids():
    user = "user-shared"
    tasks = [f"Task {i}" for i in range(4)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run_simple_task, user, task) for task in tasks]
        results = [f.result() for f in futures]

    # All runs are for the same user but should have distinct run_ids.
    run_ids = {r.get("run_id") for r in results}
    assert len(run_ids) == len(results)
    for result in results:
        assert result.get("user_id") == user
        assert isinstance(result.get("steps"), list)
        assert isinstance(result.get("logs"), list)
