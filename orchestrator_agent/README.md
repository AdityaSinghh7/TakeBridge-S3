# Orchestrator Agent (starter)

This package houses the lightweight orchestrator that will mediate between the MCP agent and the computer-use agent.

- `data_types.py` – canonical, single-source-of-truth data contracts for requests, steps, results, and tenant context.
- `runtime.py` – outer loop that tracks budget, intermediate state, and dispatches steps to the correct agent target. Concurrency is controlled with an asyncio semaphore for multi-tenant runs.
- `__main__.py` – tiny executable entrypoint (`python -m orchestrator_agent`) to prove the wiring.
- `system_prompt.py` – system prompt string + accessor for attaching to downstream model calls.

Where things will live once fleshed out:
- Agent bridges: drop MCP/computer-use adapters alongside `runtime.py` to replace the stubbed `_dispatch_step`.
- Planning: swap `_bootstrap_plan` with a planner that decomposes tasks via MCP before execution.
- Persistence/telemetry: `RunState` exposes `intermediate` for run-local data; hook logging + cost tracking via `shared.logger.StructuredLogger` and `shared.token_cost_tracker.TOKEN_TRACKER`.
