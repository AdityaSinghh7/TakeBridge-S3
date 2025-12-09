from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from computer_use_agent.agent_s import AgentS3
from server.api.controller_client import VMControllerClient
from computer_use_agent.grounding.grounding_agent import OSWorldACI
from computer_use_agent.orchestrator.data_types import (
    DEFAULT_CONTROLLER_CONFIG,
    DEFAULT_GROUNDING_CONFIG,
    DEFAULT_WORKER_CONFIG,
    OrchestrateRequest,
    RunnerResult,
    RunnerStep,
)
from computer_use_agent.utils.local_env import LocalEnv
from computer_use_agent.utils.behavior_narrator import BehaviorNarrator
from shared.latency_logger import LATENCY_LOGGER
from shared.streaming import emit_event
from shared import agent_signal
from shared.run_context import RUN_LOG_ID
from shared.db.workflow_runs import merge_agent_states, mark_run_attention

logger = logging.getLogger(__name__)

agent_signal.register_signal_handlers()


class ControllerEnv:
    """Minimal environment wrapper exposing a controller attribute."""

    def __init__(self, controller: VMControllerClient) -> None:
        self.controller = controller


def _read_text_prompt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _execute_remote_pyautogui(controller: VMControllerClient, code: str) -> Dict[str, Any]:
    """Execute the generated pyautogui script on the remote VM via the controller."""
    script = code.strip()
    payload = base64.b64encode(script.encode("utf-8")).decode("utf-8")
    # Prefer single-line command on Windows to avoid CreateProcess arg issues.
    # Keep payload quoted so it survives JSON transport on Windows.
    python_cmd_template = "import base64, sys; exec(base64.b64decode(\"{payload}\").decode())"
    # Choose python executable based on remote platform (python3 may not exist on Windows)
    python_exe = "python3"
    try:
        platform_val = controller.get_platform()
        if isinstance(platform_val, str) and platform_val.lower().startswith("win"):
            python_exe = "python"
    except Exception:
        platform_val = None  # fallback
    python_cmd = python_cmd_template.format(payload=payload)

    try:
        preview = script[:200].replace("\n", "\\n")
        logger.info(
            "Executing remote pyautogui via %s platform=%s - code preview: %s",
            python_exe,
            str(platform_val),
            preview,
        )
    except Exception:
        logger.debug("Executing remote pyautogui via %s", python_exe)

    return controller.execute([python_exe, "-c", python_cmd])


def _build_grounding_prompts(
    grounding_system_prompt: Optional[str],
) -> Dict[str, Any]:
    text_span_path = Path("computer_use_agent/grounding/text_span_prompt.txt")
    text_span_system = _read_text_prompt(text_span_path).strip()
    return {
        "grounding_service": {
            "system": grounding_system_prompt,
            "user_format": {
                "image": "data:image/webp;base64,<compressed screenshot>",
                "text": "<natural language reference>",
            },
        },
        "text_span_agent": {
            "system": text_span_system,
            "user_format": "Phrase: <phrase>\\n<Text table...> (+ screenshot attachment)",
        },
    }


def _build_trajectory_markdown(steps: List[RunnerStep], status: str, completion_reason: str) -> str:
    """Build COMPLETE self-contained markdown trajectory for orchestrator.

    CRITICAL: This trajectory must contain ALL relevant data.
    NO raw outputs or telemetry should be needed - everything is in this markdown.

    Args:
        steps: List of execution steps
        status: Final status (success, failed, timeout)
        completion_reason: Reason for completion (DONE, FAIL, MAX_STEPS_REACHED)

    Returns:
        Rich markdown trajectory showing all steps with complete data
    """
    import json

    lines = []

    for step in steps:
        lines.append(f"## Step {step.step_index}")
        lines.append("")

        # Worker output
        if step.plan:
            lines.append("### Worker Agent")
            lines.append(f"**Plan**: {step.plan}")

            if step.action:
                # Truncate action for readability
                action_display = step.action
                if len(action_display) > 300:
                    action_display = action_display[:300] + "... (truncated)"
                lines.append(f"**Action**: `{action_display}`")

            if step.execution_result:
                result_json = json.dumps(step.execution_result, indent=2, ensure_ascii=False)
                lines.append(f"**Execution Result**:\n```json\n{result_json}\n```")

        # Reflection output
        if step.reflection:
            lines.append("")
            lines.append("### Reflection Agent")
            lines.append(f"**Reflection**: {step.reflection}")

            if step.reflection_thoughts:
                lines.append(f"**Thoughts**: {step.reflection_thoughts}")

        # Behaviour narrator output
        if step.behavior_fact_answer:
            lines.append("")
            lines.append("### Behaviour Narrator")
            lines.append(f"**Observation**: {step.behavior_fact_answer}")

            if step.behavior_fact_thoughts:
                lines.append(f"**Analysis**: {step.behavior_fact_thoughts}")

        # Code agent output (if present)
        if step.info:
            code_output = step.info.get("code_agent_output")
            if code_output:
                lines.append("")
                lines.append("### Code Agent")

                if isinstance(code_output, dict):
                    # Extract code and result
                    summary = code_output.get("summary", "")
                    completion = code_output.get("completion_reason", "")
                    exec_history = code_output.get("execution_history", [])

                    if summary:
                        lines.append(f"**Summary**: {summary}")
                    if completion:
                        lines.append(f"**Completion**: {completion}")

                    # Show execution history (limit to last 3 steps)
                    if exec_history:
                        lines.append("**Execution History**:")
                        for hist_step in exec_history[-3:]:  # Last 3 steps only
                            step_num = hist_step.get("step", "?")
                            action = hist_step.get("action", "")
                            thoughts = hist_step.get("thoughts", "")

                            lines.append(f"  Step {step_num}:")
                            if action and action not in ("DONE", "FAIL"):
                                # Truncate code
                                code_display = action
                                if len(code_display) > 400:
                                    code_display = code_display[:400] + "... (truncated)"
                                lines.append(f"    **Code**: ```\n{code_display}\n```")
                            else:
                                lines.append(f"    **Action**: {action}")
                            if thoughts:
                                thoughts_display = thoughts[:200]
                                lines.append(f"    **Thoughts**: {thoughts_display}")
                else:
                    # Fallback: show as string
                    output_str = str(code_output)
                    if len(output_str) > 500:
                        output_str = output_str[:500] + "... (truncated)"
                    lines.append(f"**Output**: {output_str}")

        # Handback to human output (if present)
        if step.handback_request:
            lines.append("")
            lines.append("### Handback to Human")
            lines.append(f"**Request**: {step.handback_request}")
            lines.append("**Status**: Awaiting human intervention")

        lines.append("")  # Blank line between steps

    # Final status
    lines.append("## Final Status")
    lines.append(f"**Status**: {status}")
    lines.append(f"**Completion Reason**: {completion_reason}")

    return "\n".join(lines)


def runner(
    request: OrchestrateRequest,
    orchestrator_context: Optional[Dict[str, Any]] = None,
) -> RunnerResult:
    """
    Execute the computer-use agent runner loop.
    
    Args:
        request: The orchestration request with task and configuration
        orchestrator_context: Optional context containing:
            - orchestrator_state: Serialized orchestrator RunState for handback snapshots
            - handback_inference_context: Inference result from previous handback to inject
    """
    agent_signal.clear_signal_state()
    controller = VMControllerClient(
        base_url=request.controller.base_url,
        host=request.controller.host,
        port=request.controller.port,
        timeout=request.controller.timeout,
    )
    logger.info(
        "Resolved controller connection: base_url=%s host=%s port=%s timeout=%s",
        controller.base_url,
        request.controller.host,
        request.controller.port,
        request.controller.timeout,
    )
    
    # Extract orchestrator state and handback inference from context
    _orchestrator_state = None
    _handback_inference_context = None
    if orchestrator_context:
        _orchestrator_state = orchestrator_context.get("orchestrator_state")
        _handback_inference_context = orchestrator_context.get("handback_inference_context")

    try:
        screen_info = controller.screen_size()
        screen_width = int(screen_info.get("width", 1920))
        screen_height = int(screen_info.get("height", 1080))
    except Exception:
        screen_width = 1920
        screen_height = 1080

    platform = request.platform or controller.get_platform()

    env = (
        LocalEnv()
        if request.enable_code_execution
        else ControllerEnv(controller)
    )

    grounding_cfg = request.grounding
    worker_cfg = request.worker
    worker_post_action_delay = max(worker_cfg.post_action_worker_delay, 0.0)

    def _perform_run() -> RunnerResult:
        # Store orchestrator state in closure for handback capture
        nonlocal _orchestrator_state, _handback_inference_context
        
        grounding_agent = OSWorldACI(
            env=env,
            platform=platform.lower() if platform else "unknown",
            engine_params_for_generation=grounding_cfg.engine_params_for_generation,
            engine_params_for_grounding=grounding_cfg.engine_params_for_grounding,
            width=screen_width,
            height=screen_height,
            code_agent_budget=grounding_cfg.code_agent_budget,
            code_agent_engine_params=grounding_cfg.code_agent_engine_params,
            grounding_base_url=grounding_cfg.grounding_base_url,
            grounding_system_prompt=grounding_cfg.grounding_system_prompt,
            grounding_timeout=grounding_cfg.grounding_timeout,
            grounding_max_retries=grounding_cfg.grounding_max_retries,
            grounding_api_key=grounding_cfg.grounding_api_key,
        )
        
        # Inject handback inference context if this is a continuation after handback
        if _handback_inference_context:
            grounding_agent.handback_inference = _handback_inference_context
            logger.info("Injected handback inference context for continuation")

        agent = AgentS3(
            worker_cfg.engine_params,
            grounding_agent,
            platform=platform.lower() if platform else "unknown",
            max_trajectory_length=worker_cfg.max_trajectory_length,
            enable_reflection=worker_cfg.enable_reflection,
        )

        behavior_narrator = BehaviorNarrator(engine_params=worker_cfg.engine_params)

        max_steps = worker_cfg.max_steps
        steps: List[RunnerStep] = []
        completion_reason = "MAX_STEPS_REACHED"
        status = "in_progress"

        emit_event(
            "runner.started",
            {
                "task": request.task,
                "max_steps": max_steps,
                "platform": platform,
            },
        )

        with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "initial"}):
            before_screenshot_bytes = controller.capture_screenshot()
        previous_behavior_result: Optional[Dict[str, Any]] = None
        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()
        reflection_screenshot_bytes = before_screenshot_bytes

        for step_index in range(1, max_steps + 1):
            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()

            emit_event(
                "runner.step.started",
                {
                    "step": step_index,
                },
            )

            observation = {
                "screenshot": before_screenshot_bytes,
                "previous_behavior": previous_behavior_result,
                "reflection_screenshot": reflection_screenshot_bytes,
            }

            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()

            with LATENCY_LOGGER.measure("runner", "agent_predict", extra={"step": step_index}):
                info, actions = agent.predict(
                    instruction=request.task, observation=observation
                )
            action = actions[0] if actions else ""
            exec_code = info.get("exec_code", action)

            execution_result: Dict[str, Any] = {}
            normalized = action.strip().upper()
            did_click_action = False

            agent_payload = {
                "plan": info.get("plan"),
                "reflection": info.get("reflection"),
                "reflection_thoughts": info.get("reflection_thoughts"),
            }
            if info.get("code_agent_output") is not None:
                agent_payload["code_agent_output"] = info.get("code_agent_output")
            emit_event(
                "runner.step.agent_response",
                {
                    "step": step_index,
                    "action": action,
                    "exec_code": exec_code,
                    "normalized_action": normalized,
                    "info": {k: v for k, v in agent_payload.items() if v is not None},
                },
            )

            after_screenshot_bytes = before_screenshot_bytes
            execution_mode = "noop"
            execution_details: Dict[str, Any] = {"step": step_index}

            if normalized == "DONE":
                execution_mode = "final_screenshot"
                emit_event(
                    "runner.step.execution.started",
                    {
                        "step": step_index,
                        "mode": execution_mode,
                    },
                )
                status = "success"
                completion_reason = "DONE"
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "after", "step": step_index}):
                    after_screenshot_bytes = controller.capture_screenshot()
                execution_details["status"] = status
                execution_details["completion_reason"] = completion_reason
            elif normalized == "FAIL":
                execution_mode = "failure_screenshot"
                emit_event(
                    "runner.step.execution.started",
                    {
                        "step": step_index,
                        "mode": execution_mode,
                    },
                )
                status = "failed"
                completion_reason = "FAIL"
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "after", "step": step_index}):
                    after_screenshot_bytes = controller.capture_screenshot()
                execution_details["status"] = status
                execution_details["completion_reason"] = completion_reason
            elif action.strip().startswith("HANDBACK_TO_HUMAN:"):
                # Handback to human - extract request and capture state
                execution_mode = "handback_to_human"
                handback_request = action.strip()[len("HANDBACK_TO_HUMAN:"):].strip()
                emit_event(
                    "runner.step.execution.started",
                    {
                        "step": step_index,
                        "mode": execution_mode,
                        "handback_request": handback_request,
                    },
                )
                
                # Capture handback screenshot
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "handback", "step": step_index}):
                    handback_screenshot_bytes = controller.capture_screenshot()
                handback_screenshot_b64 = base64.b64encode(handback_screenshot_bytes).decode("utf-8")
                
                # Build partial trajectory for snapshot
                partial_trajectory_md = _build_trajectory_markdown(steps, "attention", "HANDOFF_TO_HUMAN")
                
                # Get run_id from context
                run_id = RUN_LOG_ID.get()
                handback_timestamp = datetime.now(timezone.utc).isoformat()
                
                if run_id:
                    # Build FULL cross-agent snapshot
                    from shared.db.workflow_runs import get_agent_states, update_agent_states
                    from dataclasses import asdict
                    
                    # Read existing agent_states to preserve MCP state if present
                    existing_states = {}
                    try:
                        existing_states = get_agent_states(run_id)
                    except Exception as e:
                        logger.warning("Could not read existing agent_states: %s", e)
                    
                    # Build the full snapshot
                    full_snapshot = {
                        "version": 1,
                        "updated_at": handback_timestamp,
                    }
                    
                    # 1. Include orchestrator state if available
                    if _orchestrator_state:
                        full_snapshot["orchestrator"] = _orchestrator_state
                    elif existing_states.get("orchestrator"):
                        # Preserve existing orchestrator state
                        full_snapshot["orchestrator"] = existing_states["orchestrator"]
                    
                    # 2. Build computer_use state
                    computer_use_snapshot = {
                        "status": "attention",
                        "completion_reason": "HANDOFF_TO_HUMAN",
                        "step_index_next": step_index + 1,
                        "steps": [asdict(s) for s in steps],
                        "handback": {
                            "request": handback_request,
                            "screenshot_b64": handback_screenshot_b64,
                            "timestamp": handback_timestamp,
                            "step_index": step_index,
                        },
                        "runner": {
                            "trajectory_md": partial_trajectory_md,
                        },
                    }
                    
                    # 3. Include MCP state if present in existing states
                    agents_section = {"computer_use": computer_use_snapshot}
                    if existing_states.get("agents", {}).get("mcp"):
                        agents_section["mcp"] = existing_states["agents"]["mcp"]
                    
                    full_snapshot["agents"] = agents_section
                    
                    try:
                        # Write the full snapshot (replaces existing)
                        update_agent_states(run_id, full_snapshot)
                        # Mark run as needing attention
                        mark_run_attention(run_id, summary=f"Human attention required: {handback_request[:100]}")
                        logger.info("Full handback snapshot persisted for run_id=%s", run_id)
                    except Exception as e:
                        logger.error("Failed to persist handback state: %s", e)
                    
                    # Emit human_attention.required event
                    emit_event(
                        "human_attention.required",
                        {
                            "request": handback_request,
                            "step_index": step_index,
                            "timestamp": handback_timestamp,
                            "run_id": run_id,
                        },
                    )
                else:
                    logger.warning("No run_id in context; handback state not persisted")
                
                # Record the handback step
                steps.append(
                    RunnerStep(
                        step_index=step_index,
                        plan=info.get("plan", ""),
                        action=action,
                        exec_code=exec_code,
                        execution_result={},
                        reflection=info.get("reflection"),
                        reflection_thoughts=info.get("reflection_thoughts"),
                        info=info,
                        behavior_fact_thoughts=None,
                        behavior_fact_answer=None,
                        action_kind="handback",
                        handback_request=handback_request,
                        handback_screenshot_b64=handback_screenshot_b64,
                    )
                )
                
                status = "attention"
                completion_reason = "HANDOFF_TO_HUMAN"
                after_screenshot_bytes = handback_screenshot_bytes
                execution_details["status"] = status
                execution_details["completion_reason"] = completion_reason
                execution_details["handback_request"] = handback_request
                
                emit_event(
                    "runner.step.execution.completed",
                    {
                        **execution_details,
                        "mode": execution_mode,
                        "did_click": False,
                    },
                )
                
                emit_event(
                    "runner.step.completed",
                    {
                        "step": step_index,
                        "status": status,
                        "action": action,
                        "completion_reason": completion_reason,
                    },
                )
                
                # Break out of the loop - run is paused for human attention
                break
            elif normalized in {"WAIT", "WAIT;"} or action.strip().startswith("WAIT"):
                execution_mode = "wait"
                emit_event(
                    "runner.step.execution.started",
                    {
                        "step": step_index,
                        "mode": execution_mode,
                    },
                )
                agent_signal.sleep_with_interrupt(1.5)
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "after", "step": step_index}):
                    after_screenshot_bytes = controller.capture_screenshot()
            elif action.strip():
                execution_mode = "controller_execute"
                emit_event(
                    "runner.step.execution.started",
                    {
                        "step": step_index,
                        "mode": execution_mode,
                        "exec_code": exec_code,
                    },
                )
                with LATENCY_LOGGER.measure("runner", "execute_action", extra={"step": step_index}):
                    execution_result = _execute_remote_pyautogui(controller, action)
                if "pyautogui.click" in action.lower():
                    did_click_action = True
                agent_signal.sleep_with_interrupt(0.5)
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "after", "step": step_index}):
                    after_screenshot_bytes = controller.capture_screenshot()
                try:
                    agent.executor.update_latest_screenshot(after_screenshot_bytes)
                except Exception:
                    pass
                execution_details["result"] = execution_result
            else:
                execution_mode = "noop"
                emit_event(
                    "runner.step.execution.started",
                    {
                        "step": step_index,
                        "mode": execution_mode,
                    },
                )
                agent_signal.sleep_with_interrupt(0.5)
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "after", "step": step_index}):
                    after_screenshot_bytes = controller.capture_screenshot()

            emit_event(
                "runner.step.execution.completed",
                {
                    **execution_details,
                    "mode": execution_mode,
                    "did_click": did_click_action if execution_mode == "controller_execute" else False,
                },
            )

            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()

            with LATENCY_LOGGER.measure("runner", "behavior_narrator", extra={"step": step_index}):
                behavior = behavior_narrator.judge(
                    screenshot_num=step_index,
                    before_img_bytes=before_screenshot_bytes,
                    after_img_bytes=after_screenshot_bytes,
                    pyautogui_action=action,
                )

            steps.append(
                RunnerStep(
                    step_index=step_index,
                    plan=info.get("plan", ""),
                    action=action,
                    exec_code=exec_code,
                    execution_result=execution_result,
                    reflection=info.get("reflection"),
                    reflection_thoughts=info.get("reflection_thoughts"),
                    info=info,
                    behavior_fact_thoughts=behavior.get("fact_thoughts") if behavior else None,
                    behavior_fact_answer=behavior.get("fact_answer") if behavior else None,
                    action_kind="gui",
                )
            )

            previous_behavior_result = behavior

            emit_event(
                "runner.step.completed",
                {
                    "step": step_index,
                    "status": status if normalized in {"DONE", "FAIL"} else "in_progress",
                    "action": action,
                    "completion_reason": completion_reason if normalized in {"DONE", "FAIL"} else None,
                },
            )
            emit_event(
                "runner.step.behavior",
                {
                    "step": step_index,
                    "fact_answer": behavior.get("fact_answer") if behavior else None,
                    "fact_thoughts": behavior.get("fact_thoughts") if behavior else None,
                },
            )

            if normalized in {"DONE", "FAIL"}:
                break

            delayed_after_screenshot_bytes = after_screenshot_bytes
            if did_click_action and worker_post_action_delay > 0:
                agent_signal.raise_if_exit_requested()
                agent_signal.wait_for_resume()
                agent_signal.sleep_with_interrupt(worker_post_action_delay)
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "after_delayed", "step": step_index}):
                    delayed_after_screenshot_bytes = controller.capture_screenshot()

            reflection_screenshot_bytes = delayed_after_screenshot_bytes
            before_screenshot_bytes = delayed_after_screenshot_bytes

        else:
            status = "timeout"

        grounding_prompts = _build_grounding_prompts(
            grounding_cfg.grounding_system_prompt
        )

        # Generate rich markdown trajectory for orchestrator
        trajectory_md = _build_trajectory_markdown(steps, status, completion_reason)

        result = RunnerResult(
            task=request.task,
            status=status,
            completion_reason=completion_reason,
            steps=steps,
            grounding_prompts=grounding_prompts,
            trajectory_md=trajectory_md,
        )

        emit_event(
            "runner.completed",
            {
                "status": status,
                "completion_reason": completion_reason,
                "steps": len(steps),
            },
        )

        return result

    return _perform_run()

__all__ = ["runner"]
