from __future__ import annotations

"""
Lightweight orchestrator runtime.

The runtime owns the outer loop for a single orchestration run, tracks
intermediate data, and delegates steps to either the MCP agent or the
computer-use agent. Concurrency is handled at the orchestrator level so
multiple tenants can be served in parallel without mixing state.
"""

import asyncio
import contextvars
import json
import logging
from datetime import datetime
from typing import Iterable, List, Optional, Tuple, Dict, Any, Callable

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
from orchestrator_agent.exceptions import HandbackRequested
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
from shared.run_context import RUN_LOG_ID
from shared.db.workflow_runs import get_agent_states

logger = logging.getLogger(__name__)


class OrchestratorRuntime:
    """Entry point for coordinating work between agents."""

    def __init__(
        self,
        *,
        max_concurrency: int = 4,
        agent_states_provider: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> None:
        self.logger = StructuredLogger("orchestrator")
        self.cost_tracker = TOKEN_TRACKER
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.hierarchical_logger: Optional[HierarchicalLogger] = None
        self._agent_states_provider = agent_states_provider or get_agent_states
        # Pending handback inference context to inject into computer-use agent
        self._pending_inference_context: Optional[str] = None
        # Continuation context for orchestrator's own planning (includes full history)
        self._orchestrator_continuation_context: Optional[str] = None
        # Rehydrated RunState for continuation
        self._rehydrated_state: Optional[RunState] = None
        # Rehydrated state for continuation
        self._rehydrated_state: Optional[RunState] = None

    def _fetch_agent_states(self, run_id: str) -> Dict[str, Any]:
        try:
            return self._agent_states_provider(run_id) or {}
        except Exception as exc:
            logger.warning("Failed to read agent_states for run_id=%s: %s", run_id, exc)
            return {}

    async def run_task(self, request: OrchestratorRequest) -> RunState:
        """Process a single request with single-step planning."""
        agent_signal.register_signal_handlers()
        agent_signal.clear_signal_state()

        # Bind run_id to context for downstream logging (especially executor threads).
        run_token = None
        if request.request_id:
            run_token = RUN_LOG_ID.set(request.request_id)

        # Initialize hierarchical logger and set in context
        self.hierarchical_logger = HierarchicalLogger(request.task)
        set_hierarchical_logger(self.hierarchical_logger)
        orch_logger = self.hierarchical_logger.get_agent_logger("orchestrator")

        tenant_id = request.tenant.tenant_id if request.tenant else "unknown"
        request_id = request.request_id or (
            request.tenant.request_id if request.tenant else "unknown"
        )
        
        # Check for continuation state from handback resume
        self._pending_inference_context = None
        self._orchestrator_continuation_context = None
        if request.request_id:
            self._load_continuation_context(request.request_id)

        # Attempt to rehydrate RunState from agent_states (handback/resume)
        state = self._rehydrate_state_if_available(request) or RunState(
            request=request,
            plan=[],  # No pre-planned steps - planning happens each iteration
            cost_baseline=self.cost_tracker.total_cost_usd,
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
                "task_preview": decision.get("task", ""),
                "reasoning": decision.get("reasoning"),
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

                try:
                    result = await self._dispatch_step(step, state)
                    state.record_result(result)

                    # Emit SSE event: step completed
                    emit_event("orchestrator.step.completed", {
                        "step_id": step.step_id,
                        "status": result.status,
                        "success": result.success,
                    })
                except HandbackRequested as hb:
                    # Handback to human requested - stop the orchestrator loop
                    logger.info(
                        "Orchestrator stopping due to handback request: %s (run_id=%s)",
                        hb.request,
                        hb.run_id,
                    )
                    state.record_intermediate("completion_status", "attention")
                    state.record_intermediate("handback_request", hb.request)
                    emit_event("orchestrator.handback.stopping", {
                        "request": hb.request,
                        "run_id": hb.run_id,
                    })
                    orch_logger.log_event("handback.stopping", {
                        "request": hb.request,
                        "run_id": hb.run_id,
                    })
                    break  # Exit the main loop

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
            "status": "success",
        })

        # Log to hierarchical logger
        orch_logger.log_event("task.completed", {
            "total_steps": len(state.results),
            "successful_steps": sum(1 for r in state.results if r.success),
            "failed_steps": sum(1 for r in state.results if not r.success),
        })

        if run_token:
            RUN_LOG_ID.reset(run_token)
        return state

    async def run_many(self, requests: Iterable[OrchestratorRequest]) -> List[RunState]:
        """Run many requests concurrently while honoring the semaphore."""
        tasks = [asyncio.create_task(self._guarded_run(request)) for request in requests]
        return await asyncio.gather(*tasks)

    async def _guarded_run(self, request: OrchestratorRequest) -> RunState:
        async with self._semaphore:
            return await self.run_task(request)

    def _rehydrate_state_if_available(self, request: OrchestratorRequest) -> Optional[RunState]:
        """
        Rebuild RunState from persisted agent_states for continuation (handback/resume).

        - Restores orchestrator.plan/results/intermediate/cost_baseline when present.
        - Appends last_resume_step (translated CU result) if present under agents.orchestrator.
        - Sets continuation context for prompt building if stored by CU handback resume.
        """
        run_id = request.request_id or (request.tenant.request_id if request.tenant else None)
        if not run_id:
            return None

        agent_states = self._fetch_agent_states(run_id)
        if not agent_states:
            return None

        orch_state = agent_states.get("orchestrator") if isinstance(agent_states, dict) else None
        if not isinstance(orch_state, dict):
            return None

        def _parse_dt(val: Any) -> Any:
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val)
                except Exception:
                    return val
            return val

        def _hydrate_planned(p: Dict[str, Any]) -> PlannedStep:
            return PlannedStep(
                step_id=p.get("step_id") or p.get("id") or generate_step_id("rehydrated"),
                next_task=p.get("next_task", ""),
                max_steps=p.get("max_steps", 1),
                verification=p.get("verification", "Step completed"),
                target=p.get("target") or "computer_use",
                description=p.get("description"),
                depends_on=p.get("depends_on") or [],
                hints=p.get("hints") or {},
                metadata=p.get("metadata") or {},
                requested_at=_parse_dt(p.get("requested_at")) or datetime.utcnow(),
            )

        def _hydrate_result(r: Dict[str, Any]) -> StepResult:
            return StepResult(
                step_id=r.get("step_id") or r.get("id") or generate_step_id("rehydrated"),
                target=r.get("target") or "computer_use",
                next_task=r.get("next_task", ""),
                verification=r.get("verification", "Step completed"),
                status=r.get("status") or "completed",
                success=r.get("success"),
                max_steps=r.get("max_steps"),
                description=r.get("description"),
                depends_on=r.get("depends_on") or [],
                hints=r.get("hints") or {},
                metadata=r.get("metadata") or {},
                output=r.get("output") or {},
                error=r.get("error"),
                started_at=_parse_dt(r.get("started_at")),
                finished_at=_parse_dt(r.get("finished_at")),
                artifacts=r.get("artifacts") or {},
            )

        plan_raw = orch_state.get("plan") or []
        results_raw = orch_state.get("results") or []
        plan: List[PlannedStep] = []
        results: List[StepResult] = []

        for p in plan_raw:
            try:
                plan.append(_hydrate_planned(p))
            except Exception as exc:
                logger.warning("Failed to hydrate PlannedStep: %s", exc)

        for r in results_raw:
            try:
                results.append(_hydrate_result(r))
            except Exception as exc:
                logger.warning("Failed to hydrate StepResult: %s", exc)

        def _append_resume_result(resume_dict: Dict[str, Any], source: str) -> bool:
            try:
                existing_ids = {r.step_id for r in results if getattr(r, "step_id", None)}
                hydrated = _hydrate_result(resume_dict)
                if hydrated.step_id not in existing_ids:
                    results.append(hydrated)
                    logger.info("Appended %s for run_id=%s", source, run_id)
                else:
                    logger.info(
                        "Skipped appending duplicate %s (step_id=%s) for run_id=%s",
                        source,
                        hydrated.step_id,
                        run_id,
                    )
                return True
            except Exception as exc:
                logger.warning("Failed to hydrate %s: %s", source, exc)
                return False

        appended_resume = False

        # Append last_resume_step if stored under agents.orchestrator
        last_resume = (
            agent_states.get("agents", {})
            .get("orchestrator", {})
            .get("last_resume_step")
        )
        if isinstance(last_resume, dict):
            appended_resume = _append_resume_result(last_resume, "last_resume_step")

        if not appended_resume:
            resume_payload = (
                agent_states.get("agents", {})
                .get("computer_use", {})
                .get("resume")
            )
            if isinstance(resume_payload, dict):
                resume_step_result = resume_payload.get("step_result")
                if isinstance(resume_step_result, dict):
                    appended_resume = _append_resume_result(
                        resume_step_result,
                        "computer_use.resume.step_result",
                    )
                elif isinstance(resume_payload.get("translated"), dict):
                    translated = resume_payload.get("translated") or {}
                    resume_task = translated.get("task") or request.task
                    resume_success = bool(
                        translated.get("overall_success", translated.get("success", True))
                    )
                    status: StepStatus = "completed" if resume_success else "failed"
                    step_id = f"resume-{run_id}" if run_id else generate_step_id("resume")
                    output = {
                        "target": "computer_use",
                        "translated": translated,
                        "raw_ref": f"{step_id}:raw",
                        "usage": {},
                    }
                    minimal_result = StepResult(
                        step_id=step_id,
                        target="computer_use",
                        next_task=resume_task,
                        verification="resume",
                        status=status,
                        success=resume_success,
                        output=output,
                        error=translated.get("error"),
                    )
                    existing_ids = {r.step_id for r in results if getattr(r, "step_id", None)}
                    if minimal_result.step_id not in existing_ids:
                        results.append(minimal_result)
                        logger.info(
                            "Appended resume translated fallback for run_id=%s",
                            run_id,
                        )
                    else:
                        logger.info(
                            "Skipped appending duplicate resume translated fallback (step_id=%s) for run_id=%s",
                            minimal_result.step_id,
                            run_id,
                        )
                    appended_resume = True

        cost_baseline = orch_state.get("cost_baseline", self.cost_tracker.total_cost_usd)
        intermediate = orch_state.get("intermediate") or {}

        rehydrated = RunState(
            request=request,
            plan=plan,
            results=results,
            intermediate=intermediate,
            cost_baseline=cost_baseline,
        )

        # Preserve continuation context for prompts if stored on CU agent
        continuation_ctx = (
            agent_states.get("agents", {})
            .get("computer_use", {})
            .get("continuation", {})
            .get("inference_context")
        )
        if continuation_ctx:
            self._orchestrator_continuation_context = continuation_ctx

        self._rehydrated_state = rehydrated
        return rehydrated
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
            continuation_context=self._orchestrator_continuation_context,
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
            trajectory = await self._call_agent(step, state.request, state)
            logger.info(
                "runtime.translate.start target=%s step=%s trajectory_len=%s",
                step.target,
                step.step_id,
                len(trajectory),
            )
            translated = translate_step_output(
                task=step.next_task,
                target=step.target,
                trajectory=trajectory,
                debug_step_id=step.step_id,
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
        except HandbackRequested:
            # Re-raise HandbackRequested to propagate to the main loop
            # This must come before the generic Exception handler
            raise
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
        Call LLM to decide the next step using the shared LLM client.

        Args:
            system_prompt: The dynamic system prompt with capabilities and context
            request: Orchestration request

        Returns:
            Decision dict: {"type": "next_step"|"task_complete"|"task_impossible", ...}

        Raises:
            Exception if LLM call fails after retry
        """
        from shared.llm_client import LLMClient, extract_assistant_text

        # Simple user message - just the task
        user_message = f"What should be the next step to accomplish this goal?"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Use LLMClient wrapper for better retry logic
        client = LLMClient(
            default_model="o4-mini",
            default_reasoning_effort="medium",
            max_retries=1,  # We'll retry once internally
        )

        # Retry on invalid JSON with a stronger JSON-only reminder and higher output cap.
        max_attempts = 3
        retry_note = (
            "Your previous response was invalid JSON. "
            "Return a single valid JSON object that matches the schema. "
            "Ensure all strings are properly escaped and closed. "
            "Do not include any extra text."
        )
        for attempt in range(max_attempts):
            try:
                if attempt == 0:
                    attempt_messages = messages
                else:
                    attempt_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "system", "content": retry_note},
                        {"role": "user", "content": user_message},
                    ]
                response = client.create_response(
                    model="o4-mini",
                    messages=attempt_messages,
                    text={"format": {"type": "json_object"}},
                    reasoning_effort="high",
                )

                # Extract assistant text from Responses API output
                text = extract_assistant_text(response)
                result = json.loads(text)

                # Validate response type
                if result.get("type") not in ["next_step", "task_complete", "task_impossible"]:
                    logger.info(f"Retryying Orchestrator LLM with invalid response type: {result.get('type')}")
                    raise ValueError(f"Invalid response type: {result.get('type')}")

                return result

            except json.JSONDecodeError as e:
                logger.error(
                    "LLM returned invalid JSON (attempt %s/%s): %s",
                    attempt + 1,
                    max_attempts,
                    e,
                )
                if attempt + 1 < max_attempts:
                    continue
                logger.critical(f"LLM retry failed with invalid JSON: {e}")
                raise

            except Exception as e:
                if attempt == 0:
                    logger.error(f"Orchestrator LLM failed, retrying: {e}")
                    continue
                else:
                    logger.critical(f"Orchestrator LLM retry failed: {e}")
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

    def _load_continuation_context(self, run_id: str) -> None:
        """
        Check if this run has a continuation state from a handback resume.
        If so, extract:
        1. inference_context - for the computer-use agent (injected into its context)
        2. The same context is used by the orchestrator for planning decisions
        """
        try:
            agent_states = self._fetch_agent_states(run_id)
            if not agent_states:
                return
            
            continuation = (
                agent_states.get("agents", {})
                .get("computer_use", {})
                .get("continuation", {})
            )
            
            if continuation.get("should_inject_inference"):
                inference_context = continuation.get("inference_context")
                if inference_context:
                    # Store for computer-use agent injection
                    self._pending_inference_context = inference_context
                    # Also store for orchestrator's own planning (same context)
                    self._orchestrator_continuation_context = inference_context
                    logger.info(
                        "Loaded continuation context for run_id=%s (resume_from_step=%s)",
                        run_id,
                        continuation.get("resume_from_step"),
                    )
        except Exception as e:
            logger.warning("Failed to load continuation context for run_id=%s: %s", run_id, e)

    async def _call_agent(
        self, step: PlannedStep, request: OrchestratorRequest, state: "RunState"
    ) -> str:
        """Call agent bridge and return self-contained trajectory.

        IMPORTANT: Returns ONLY trajectory string, not raw_result.
        The trajectory contains all necessary data.
        """
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        run_id = getattr(request, "request_id", None)
        if run_id:
            ctx.run(RUN_LOG_ID.set, run_id)
        
        # Serialize orchestrator state for handback capture
        orchestrator_state = state.to_dict() if state else None
        
        # If we have pending inference context from handback, inject it into request metadata
        if self._pending_inference_context and step.target == "computer_use":
            # Make a shallow copy of metadata to inject the inference context
            updated_metadata = dict(request.metadata) if request.metadata else {}
            updated_metadata["handback_inference_context"] = self._pending_inference_context
            # Clear pending context after use
            self._pending_inference_context = None
            logger.info("Injecting handback inference context into computer-use dispatch")
            # Create a modified request with the updated metadata
            # Note: We modify in place since this is a single dispatch
            original_metadata = request.metadata
            request.metadata = updated_metadata
            try:
                return await loop.run_in_executor(
                    None, lambda: ctx.run(run_agent_bridge, step.target, request, step, orchestrator_state)
                )
            finally:
                # Restore original metadata
                request.metadata = original_metadata
        
        return await loop.run_in_executor(
            None, lambda: ctx.run(run_agent_bridge, step.target, request, step, orchestrator_state)
        )


__all__ = ["OrchestratorRuntime"]
