from __future__ import annotations

"""
Thin executable wrapper so the orchestrator can be invoked via
`python -m orchestrator_agent`.
"""

import asyncio
import logging

from orchestrator_agent.data_types import Budget, OrchestratorRequest
from orchestrator_agent.runtime import OrchestratorRuntime


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    runtime = OrchestratorRuntime()
    request = OrchestratorRequest.from_task(
        tenant_id="dev",
        task="Draft plan and execute steps for a demo task.",
        budget=Budget(max_steps=2, max_cost_usd=1.0),
        metadata={"platform": "macos"},
    )
    state = await runtime.run_task(request)

    print("Orchestrator finished run:")
    for result in state.results:
        print(f"- step_id={result.step_id} target={result.target} status={result.status}")


if __name__ == "__main__":
    asyncio.run(_main())
