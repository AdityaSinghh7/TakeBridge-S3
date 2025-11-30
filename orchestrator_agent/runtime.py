from __future__ import annotations

"""
Lightweight orchestrator runtime.

The runtime owns the outer loop for a single orchestration run, tracks
intermediate data, and delegates steps to either the MCP agent or the
computer-use agent. Concurrency is handled at the orchestrator level so
multiple tenants can be served in parallel without mixing state.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Iterable, List, Optional, Tuple, Dict, Any

from orchestrator_agent.data_types import (
    AgentTarget,
    OrchestratorRequest,
    PlannedStep,
    RunState,
    StepResult,
    StepStatus,
    generate_step_id,
)
from orchestrator_agent.bridges import run_agent_bridge
from orchestrator_agent.translator import translate_step_output
from orchestrator_agent.capabilities import build_capability_context
from orchestrator_agent.system_prompt import build_system_prompt
from shared.logger import StructuredLogger
from shared.token_cost_tracker import TOKEN_TRACKER
from shared import agent_signal
from shared.streaming import emit_event
from shared.hierarchical_logger import (
    HierarchicalLogger,
    set_hierarchical_logger,
    get_hierarchical_logger,
)

logger = logging.getLogger(__name__)


class OrchestratorRuntime:
    """Entry point for coordinating work between agents."""

    def __init__(self, *, max_concurrency: int = 4) -> None:
        self.logger = StructuredLogger("orchestrator")
        self.cost_tracker = TOKEN_TRACKER
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.hierarchical_logger: Optional[HierarchicalLogger] = None

    async def run_task(self, request: OrchestratorRequest) -> RunState:
        """Process a single request with single-step planning."""
        agent_signal.register_signal_handlers()
        agent_signal.clear_signal_state()

        # Initialize hierarchical logger and set in context
        self.hierarchical_logger = HierarchicalLogger(request.task)
        set_hierarchical_logger(self.hierarchical_logger)
        orch_logger = self.hierarchical_logger.get_agent_logger("orchestrator")

        state = RunState(
            request=request,
            plan=[],  # No pre-planned steps - planning happens each iteration
            cost_baseline=self.cost_tracker.total_cost_usd,
        )
        tenant_id = request.tenant.tenant_id if request.tenant else "unknown"
        request_id = request.request_id or (
            request.tenant.request_id if request.tenant else "unknown"
        )
        self.logger.info(
            f"Starting orchestration request_id={request_id} tenant={tenant_id}"
        )

        # Emit SSE event: task started
        emit_event("orchestrator.task.started", {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "task": request.task[:100],
            "max_steps": request.budget.max_steps,
            "tool_constraints": request.tool_constraints.to_dict() if request.tool_constraints else None,
        })

        # Log to hierarchical logger
        orch_logger.log_event("task.started", {
            "task": request.task,
            "max_steps": request.budget.max_steps,
            "tenant_id": tenant_id,
            "request_id": request_id,
            "tool_constraints": request.tool_constraints.to_dict() if request.tool_constraints else None,
        })

        # Main planning loop - get next step, execute, repeat
        while state.within_limits(self.cost_tracker.total_cost_usd):
            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()

            # Determine if last step failed
            last_failed = (
                len(state.results) > 0 and state.results[-1].status == "failed"
            )

            # Ask orchestrator: what's the next step?
            decision = self._get_next_step(request, state, last_failed)

            # Emit SSE event: planning completed
            emit_event("orchestrator.planning.completed", {
                "decision_type": decision["type"],
                "target": decision.get("target"),
                "task_preview": decision.get("task", "")[:80],
            })

            if decision["type"] == "task_complete":
                self.logger.info(f"Task complete: {decision.get('reasoning')}")
                orch_logger.log_event("task.complete", {
                    "reasoning": decision.get("reasoning"),
                })
                break

            elif decision["type"] == "task_impossible":
                self.logger.info(f"Task impossible: {decision.get('reasoning')}")
                orch_logger.log_event("task.impossible", {
                    "reasoning": decision.get("reasoning"),
                })
                # Record as a special terminal result
                state.record_intermediate("completion_status", "impossible")
                state.record_intermediate("impossible_reason", decision.get("reasoning"))
                break

            elif decision["type"] == "next_step":
                # Create and execute the step
                step = PlannedStep(
                    step_id=self._build_step_id(f"step-{len(state.results)}"),
                    next_task=decision["task"],
                    max_steps=request.max_steps,
                    verification="Step completed",
                    target=decision["target"],
                    description=decision["task"][:100],
                )
                state.plan.append(step)  # Add to history

                self.logger.info(
                    f"Next step: {decision['target']} - {decision['task'][:80]}"
                )

                # Emit SSE event: step dispatching
                emit_event("orchestrator.step.dispatching", {
                    "step_id": step.step_id,
                    "target": step.target,
                    "task": step.next_task[:100],
                })

                result = await self._dispatch_step(step, state)
                state.record_result(result)

                # Emit SSE event: step completed
                emit_event("orchestrator.step.completed", {
                    "step_id": step.step_id,
                    "status": result.status,
                    "success": result.success,
                })

            else:
                logger.error(f"Unknown decision type: {decision.get('type')}")
                break

            # Budget check
            if state.cost_exceeded(self.cost_tracker.total_cost_usd):
                self.logger.info("Budget exceeded; stopping.")
                break

            # Step limit check
            if len(state.results) >= request.budget.max_steps:
                self.logger.info(
                    f"Step limit reached ({request.budget.max_steps}); stopping."
                )
                break

        # Emit SSE event: task completed
        emit_event("orchestrator.task.completed", {
            "total_steps": len(state.results),
            "status": "success" if all(r.success for r in state.results) else "partial",
        })

        # Log to hierarchical logger
        orch_logger.log_event("task.completed", {
            "total_steps": len(state.results),
            "successful_steps": sum(1 for r in state.results if r.success),
            "failed_steps": sum(1 for r in state.results if not r.success),
        })

        return state

    async def run_many(self, requests: Iterable[OrchestratorRequest]) -> List[RunState]:
        """Run many requests concurrently while honoring the semaphore."""
        tasks = [asyncio.create_task(self._guarded_run(request)) for request in requests]
        return await asyncio.gather(*tasks)

    async def _guarded_run(self, request: OrchestratorRequest) -> RunState:
        async with self._semaphore:
            return await self.run_task(request)

    def _get_next_step(
        self, request: OrchestratorRequest, state: RunState, last_failed: bool
    ) -> Dict[str, Any]:
        """
        Ask the orchestrator LLM what the next step should be.

        Returns a decision dict with:
        - {"type": "next_step", "target": "mcp"|"computer_use", "task": "...", "reasoning": "..."}
        - {"type": "task_complete", "reasoning": "..."}
        - {"type": "task_impossible", "reasoning": "..."}
        """
        # Fetch capabilities
        try:
            capabilities = self._get_cached_capabilities(request)
        except Exception as e:
            logger.warning(f"Failed to fetch capabilities: {e}")
            capabilities = {
                "mcp": {"providers": []},
                "computer": {
                    "platform": "unknown",
                    "available_apps": [],
                    "active_windows": [],
                },
            }

        # Build failure info if last step failed
        failed_step_info = None
        if last_failed and state.results:
            last_result = state.results[-1]
            failed_step_info = {
                "task": last_result.next_task,
                "target": last_result.target,
                "error": last_result.error or "Unknown error",
            }

        # Build dynamic system prompt
        system_prompt = build_system_prompt(
            request,
            capabilities,
            state=state,
            last_step_failed=last_failed,
            failed_step_info=failed_step_info,
        )

        # Call LLM
        try:
            return self._call_planner_llm(system_prompt, request)
        except Exception as e:
            # Fallback: if planning fails completely, mark as impossible
            logger.error(f"Orchestrator LLM failed: {e}")
            return {
                "type": "task_impossible",
                "reasoning": f"Orchestrator planning failed: {str(e)}",
            }

    async def _dispatch_step(self, step: PlannedStep, state: RunState) -> StepResult:
        """
        Dispatch a step to the requested agent.

        This now calls the downstream agent bridge, runs the translator, and
        records structured outputs plus usage deltas.
        """
        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()
        started_at = datetime.utcnow()
        self.logger.info(
            (
                f"Dispatching step_id={step.step_id} "
                f"target={step.target} description={step.description}"
            )
        )
        state.record_intermediate("last_target", step.target)
        state.record_intermediate("last_step_id", step.step_id)

        cost_snapshot = self._snapshot_costs()
        try:
            trajectory = await self._call_agent(step, state.request)
            logger.info(
                "runtime.translate.start target=%s step=%s trajectory_len=%s",
                step.target,
                step.step_id,
                len(trajectory),
            )
            translated = translate_step_output(
                task=step.next_task,
                step_id=step.step_id,
                target=step.target,
                trajectory=trajectory,
            )
            overall_success = bool(
                translated.get("overall_success", translated.get("success", True))
            )
            logger.info(
                "runtime.translate.done target=%s step=%s success=%s artifacts_keys=%s",
                step.target,
                step.step_id,
                overall_success,
                list((translated.get("artifacts") or {}).keys()),
            )
            usage = self._compute_usage(cost_snapshot)
            payload = {
                "target": step.target,
                "run": {
                    "tenant_id": state.request.tenant.tenant_id if state.request.tenant else None,
                    "request_id": state.request.request_id,
                    "user_id": state.request.user_id
                    or (state.request.tenant.user_id if state.request.tenant else None),
                },
                "translated": translated,
                "raw_ref": translated.get("raw_ref") or f"{step.step_id}:raw",
                "usage": usage,
            }
            status: StepStatus = "completed" if overall_success else "failed"
            success = overall_success
            error: Optional[str] = translated.get("error")
        except Exception as exc:
            payload = {
                "target": step.target,
                "error": str(exc),
                "usage": self._compute_usage(cost_snapshot),
                "raw_ref": f"{step.step_id}:raw",
            }
            status = "failed"
            success = False
            error = str(exc)

        finished_at = datetime.utcnow()
        return StepResult(
            step_id=step.step_id,
            target=step.target,
            next_task=step.next_task,
            max_steps=step.max_steps,
            verification=step.verification,
            status=status,
            success=success,
            output=payload,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _call_planner_llm(
        self, system_prompt: str, request: OrchestratorRequest
    ) -> Dict:
        """
        Call LLM to decide the next step using OAIClient Responses API.

        Args:
            system_prompt: The dynamic system prompt with capabilities and context
            request: Orchestration request

        Returns:
            Decision dict: {"type": "next_step"|"task_complete"|"task_impossible", ...}

        Raises:
            Exception if LLM call fails after retry
        """
        from shared.oai_client import OAIClient, extract_assistant_text

        # Simple user message - just the task
        user_message = f"What should be the next step to accomplish this goal?"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Use OAIClient wrapper with Responses API for better retry logic
        client = OAIClient(
            default_model="o4-mini",
            default_reasoning_effort="medium",
            max_retries=1,  # We'll retry once internally
        )

        # Retry once on failure
        for attempt in range(2):
            try:
                response = client.create_response(
                    model="o4-mini",
                    messages=messages,
                    max_output_tokens=3000,
                    reasoning_effort="high",
                )

                # Extract assistant text from Responses API output
                text = extract_assistant_text(response)
                result = json.loads(text)

                # Validate response type
                if result.get("type") not in ["next_step", "task_complete", "task_impossible"]:
                    raise ValueError(f"Invalid response type: {result.get('type')}")

                return result

            except json.JSONDecodeError as e:
                if attempt == 0:
                    logger.warning(f"LLM returned invalid JSON, retrying: {e}")
                    continue
                else:
                    logger.error(f"LLM retry failed with invalid JSON: {e}")
                    raise

            except Exception as e:
                if attempt == 0:
                    logger.warning(f"Orchestrator LLM failed, retrying: {e}")
                    continue
                else:
                    logger.error(f"Orchestrator LLM retry failed: {e}")
                    raise

    def _get_cached_capabilities(
        self, request: OrchestratorRequest
    ) -> Dict[str, Any]:
        """
        Get cached capabilities for a request.

        Args:
            request: Orchestration request

        Returns:
            Capabilities dictionary from cache
        """
        try:
            return build_capability_context(request, force_refresh=False)
        except Exception as e:
            logger.warning(f"Failed to get cached capabilities: {e}")
            return {
                "mcp": {"providers": []},
                "computer": {
                    "platform": "unknown",
                    "available_apps": [],
                    "active_windows": [],
                },
            }

    def _build_step_id(self, label: str) -> str:
        return generate_step_id(label)

    def _snapshot_costs(self) -> Tuple[int, int, int, float]:
        tracker = self.cost_tracker
        return (
            getattr(tracker, "total_input_cached", 0),
            getattr(tracker, "total_input_new", 0),
            getattr(tracker, "total_output", 0),
            getattr(tracker, "total_cost_usd", 0.0),
        )

    def _compute_usage(self, baseline: Tuple[int, int, int, float]) -> Dict[str, Any]:
        tracker = self.cost_tracker
        cached_b, new_b, out_b, cost_b = baseline
        cached = getattr(tracker, "total_input_cached", 0) - cached_b
        new = getattr(tracker, "total_input_new", 0) - new_b
        out = getattr(tracker, "total_output", 0) - out_b
        cost_delta = getattr(tracker, "total_cost_usd", 0.0) - cost_b
        return {
            "tokens": {
                "input_cached": max(int(cached), 0),
                "input_new": max(int(new), 0),
                "output": max(int(out), 0),
            },
            "cost_usd": {
                "delta": float(cost_delta),
                "run_total": float(getattr(tracker, "total_cost_usd", 0.0)),
            },
        }

    async def _call_agent(
        self, step: PlannedStep, request: OrchestratorRequest
    ) -> str:
        """Call agent bridge and return self-contained trajectory.

        IMPORTANT: Returns ONLY trajectory string, not raw_result.
        The trajectory contains all necessary data.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: run_agent_bridge(step.target, request, step)
        )


__all__ = ["OrchestratorRuntime"]
