from __future__ import annotations

import base64
import copy
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast

from computer_use_agent.agent_s import AgentS3
from computer_use_agent.worker.worker import Worker
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
from computer_use_agent.utils.computer_use_html_logger import ComputerUseHtmlLogger
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


def _prune_images_in_messages(
    messages: List[Dict[str, Any]],
    *,
    keep_image_turns: int = 2,
    persist_images: bool = False,
) -> List[Dict[str, Any]]:
    """
    Optionally remove older image parts to reduce payload size.
    If persist_images is False: strip all image parts.
    If persist_images is True: keep images in the last `keep_image_turns` messages; strip older ones.
    """
    if not messages:
        return []

    pruned: List[Dict[str, Any]] = []
    total = len(messages)
    for idx, msg in enumerate(messages):
        content = msg.get("content", [])
        if not isinstance(content, list):
            pruned.append(msg)
            continue

        new_content = []
        for part in content:
            if not isinstance(part, dict):
                new_content.append(part)
                continue
            part_type = part.get("type", "")
            if not persist_images:
                if part_type in {"image", "image_url"}:
                    continue
            else:
                # keep images only for the last keep_image_turns messages
                if part_type in {"image", "image_url"} and idx < total - keep_image_turns:
                    continue
            new_content.append(part)

        new_msg = dict(msg)
        new_msg["content"] = new_content
        pruned.append(new_msg)
    return pruned



def _build_trajectory_till_now(
    steps: List[RunnerStep],
    generator_messages: List[Dict[str, Any]],
    reflection_messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a snapshot of the trajectory so far for persistence/resume."""
    filtered_generator = [
        copy.deepcopy(msg)
        for msg in generator_messages
        if msg.get("role") not in {"developer", "system"}
    ]
    filtered_reflection = [
        copy.deepcopy(msg)
        for msg in reflection_messages
        if msg.get("role") not in {"developer", "system"}
    ]
    return {
        "generator_messages": filtered_generator,
        "reflection_messages": filtered_reflection,
    }


def _build_trajectory_markdown(
    steps: List[RunnerStep],
    status: str,
    completion_reason: str,
    *,
    is_resume_flow: bool = False,
    handback_inference: Optional[Dict[str, Any]] = None,
    include_final_status: bool = True,
) -> str:
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

    # Final status / resume context footer
    if is_resume_flow:
        lines.append("## Resume Context")
        lines.append(
            "This is a resume flow. A handback_to_human occurred in this step."
        )
        if handback_inference:
            import json as _json

            try:
                inference_json = _json.dumps(handback_inference, ensure_ascii=False, indent=2)
            except Exception:
                inference_json = str(handback_inference)
            lines.append("")
            lines.append("### Handback Inference")
            lines.append("The most recent handback result:")
            lines.append(f"```json\n{inference_json}\n```")
    elif include_final_status:
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
    controller.wait_for_health()
    
    # Extract orchestrator state and resume metadata from context
    _orchestrator_state = None
    _resume_state = None
    _inference_update = None
    _is_resume_flow = False
    if orchestrator_context:
        _orchestrator_state = orchestrator_context.get("orchestrator_state")
        _resume_state = orchestrator_context.get("resume_state")
        _inference_update = orchestrator_context.get("inference_update")
        _is_resume_flow = bool(orchestrator_context.get("is_resume_flow"))
    try:
        screen_info = controller.screen_size()
        logger.info(
            f"RECEIVED controller screen sizes: {screen_info}"
        )
        screen_width = int(screen_info.get("width", 1920))
        screen_height = int(screen_info.get("height", 1080))
        logger.info(
            f"SETTING controller screen sizes: {screen_width}x{screen_height}"
        )
    except Exception:
        logger.exception("ERROR: Failed to get controller screen sizes setting default")
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
        nonlocal _inference_update, _is_resume_flow, _orchestrator_state, _resume_state
        
        run_id = RUN_LOG_ID.get() or os.getenv("RUN_LOG_ID")
        html_logger = ComputerUseHtmlLogger(run_id)

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
        
        agent = AgentS3(
            worker_cfg.engine_params,
            grounding_agent,
            platform=platform.lower() if platform else "unknown",
            max_trajectory_length=worker_cfg.max_trajectory_length,
            enable_reflection=worker_cfg.enable_reflection,
        )

        # Rehydrate messages from inference_update when present; otherwise from resume_state prompts.
        if _inference_update:
            try:
                traj_state = _inference_update.get("trajectory_till_now") or {}
                gen_msgs = traj_state.get("generator_messages") or []
                ref_msgs = traj_state.get("reflection_messages") or []
                agent.executor.generator_agent.messages = copy.deepcopy(gen_msgs)
                agent.executor.reflection_agent.messages = copy.deepcopy(ref_msgs)
                # Mark resume mode and bump turn_count to skip initial copy
                agent.executor.resume_mode = True
            except Exception as exc:
                logger.warning("Failed to rehydrate messages from inference_update: %s", exc)

        behavior_narrator = BehaviorNarrator(engine_params=worker_cfg.engine_params)

        max_steps = worker_cfg.max_steps
        steps: List[RunnerStep] = []
        completion_reason = "MAX_STEPS_REACHED"
        status = "in_progress"
        start_step_index = 1
        previous_behavior_result: Optional[Dict[str, Any]] = None
        

        emit_event(
            "runner.started",
            {
                "task": request.task,
                "max_steps": max_steps,
                "platform": platform,
            },
        )
        html_logger.log_run_start(request.task, platform)

        before_screenshot_bytes: Optional[bytes] = None
        reflection_screenshot_bytes: Optional[bytes] = None

        # If we have a prior screenshot from handback, prefer it
        if _is_resume_flow:
            try:
                latest_b64 = _inference_update.get("latest_screenshot_b64")
                if latest_b64:
                    before_screenshot_bytes = base64.b64decode(latest_b64)
                    reflection_screenshot_bytes = before_screenshot_bytes
            except Exception as exc:
                logger.warning("Failed to decode resume screenshot: %s", exc)

        if before_screenshot_bytes is None:
            with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "initial"}):
                before_screenshot_bytes = controller.capture_screenshot()
            reflection_screenshot_bytes = before_screenshot_bytes

        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()

        for step_index in range(start_step_index, max_steps + start_step_index):
            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()

            try:
                prev_width = grounding_agent.width
                prev_height = grounding_agent.height
                screen_info = controller.screen_size()
                width = int(screen_info.get("width", prev_width))
                height = int(screen_info.get("height", prev_height))
                if width > 0 and height > 0:
                    grounding_agent.width = width
                    grounding_agent.height = height
                    if width != prev_width or height != prev_height:
                        with LATENCY_LOGGER.measure(
                            "runner",
                            "capture_screenshot",
                            extra={"phase": "resize_refresh", "step": step_index},
                        ):
                            before_screenshot_bytes = controller.capture_screenshot()
                        reflection_screenshot_bytes = before_screenshot_bytes
            except Exception as exc:
                logger.warning("Failed to refresh screen size: %s", exc)

            step_before_bytes = before_screenshot_bytes

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
                
                # Build partial trajectory markdown for persistence
                partial_trajectory_md = _build_trajectory_markdown(
                    steps,
                    status="attention",
                    completion_reason="HANDOFF_TO_HUMAN",
                    is_resume_flow=_is_resume_flow,
                    handback_inference=_inference_update.get("inference_result") if _inference_update else None,
                    include_final_status=False,
                )
                
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
                    worker_executor = cast(Worker, agent.executor)
                    generator_messages = getattr(worker_executor.generator_agent, "messages", []) or []
                    reflection_messages = getattr(worker_executor.reflection_agent, "messages", []) or []
                    reflection_messages_for_snapshot = copy.deepcopy(reflection_messages)
                    # Mirror the last assistant message from the generator into the reflection history
                    try:
                        last_assistant = next(
                            (
                                msg
                                for msg in reversed(generator_messages)
                                if isinstance(msg, dict) and msg.get("role") == "assistant"
                            ),
                            None,
                        )
                        if last_assistant:
                            reflection_messages_for_snapshot.append(copy.deepcopy(last_assistant))
                    except Exception:
                        pass

                    computer_use_snapshot = {
                        "status": "attention",
                        "completion_reason": "HANDOFF_TO_HUMAN",
                        "step_index_next": step_index + 1,
                        "trajectory_till_now": _build_trajectory_till_now(
                            steps,
                            generator_messages,
                            reflection_messages_for_snapshot,
                        ),
                        "runner": {
                            "trajectory_md": partial_trajectory_md,
                        },
                        "handback_request": handback_request,
                        "handback_screenshot_b64": handback_screenshot_b64,
                        "request": {
                            "task": request.task,
                            "worker": asdict(request.worker),
                            "grounding": asdict(request.grounding),
                            "controller": asdict(request.controller),
                            "platform": request.platform,
                            "enable_code_execution": request.enable_code_execution,
                            "tool_constraints": asdict(request.tool_constraints)
                            if request.tool_constraints
                            else None,
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

                html_logger.log_step(
                    step_index=step_index,
                    action=action,
                    exec_code=exec_code,
                    execution_mode=execution_mode,
                    status=status,
                    completion_reason=completion_reason,
                    plan=info.get("plan"),
                    reflection=info.get("reflection"),
                    handback_request=handback_request,
                    behavior_fact=None,
                    behavior_thoughts=None,
                    before_img=step_before_bytes,
                    after_img=after_screenshot_bytes,
                    delayed_after_img=None,
                    marked_before_img=None,
                    marked_after_img=None,
                    zoomed_after_img=None,
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
                agent_signal.sleep_with_interrupt(1.0)
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
                agent_signal.sleep_with_interrupt(1.0)
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
            behavior_artifacts = None
            if isinstance(behavior, dict):
                behavior_artifacts = behavior.pop("artifacts", None)

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
                html_logger.log_step(
                    step_index=step_index,
                    action=action,
                    exec_code=exec_code,
                    execution_mode=execution_mode,
                    status=status,
                    completion_reason=completion_reason,
                    plan=info.get("plan"),
                    reflection=info.get("reflection"),
                    handback_request=None,
                    behavior_fact=behavior.get("fact_answer") if behavior else None,
                    behavior_thoughts=behavior.get("fact_thoughts") if behavior else None,
                    before_img=step_before_bytes,
                    after_img=after_screenshot_bytes,
                    delayed_after_img=None,
                    marked_before_img=(behavior_artifacts or {}).get("marked_before_img_bytes"),
                    marked_after_img=(behavior_artifacts or {}).get("marked_after_img_bytes"),
                    zoomed_after_img=(behavior_artifacts or {}).get("zoomed_after_img_bytes"),
                )
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

            html_logger.log_step(
                step_index=step_index,
                action=action,
                exec_code=exec_code,
                execution_mode=execution_mode,
                status="in_progress",
                completion_reason=None,
                plan=info.get("plan"),
                reflection=info.get("reflection"),
                handback_request=None,
                behavior_fact=behavior.get("fact_answer") if behavior else None,
                behavior_thoughts=behavior.get("fact_thoughts") if behavior else None,
                before_img=step_before_bytes,
                after_img=after_screenshot_bytes,
                delayed_after_img=delayed_after_screenshot_bytes
                if delayed_after_screenshot_bytes != after_screenshot_bytes
                else None,
                marked_before_img=(behavior_artifacts or {}).get("marked_before_img_bytes"),
                marked_after_img=(behavior_artifacts or {}).get("marked_after_img_bytes"),
                zoomed_after_img=(behavior_artifacts or {}).get("zoomed_after_img_bytes"),
            )

        else:
            status = "timeout"

        grounding_prompts = _build_grounding_prompts(
            grounding_cfg.grounding_system_prompt
        )

        # Generate rich markdown trajectory for orchestrator
        trajectory_md = _build_trajectory_markdown(
            steps,
            status,
            completion_reason,
            is_resume_flow=_is_resume_flow,
            handback_inference=_inference_update.get("inference_result") if _inference_update else None,
        )

        # Extract handback request if this was a handback
        handback_request_str = None
        if completion_reason == "HANDOFF_TO_HUMAN":
            for step in reversed(steps):
                if step.handback_request:
                    handback_request_str = step.handback_request
                    break

        result = RunnerResult(
            task=request.task,
            status=status,
            completion_reason=completion_reason,
            steps=steps,
            grounding_prompts=grounding_prompts,
            trajectory_md=trajectory_md,
            handback_request=handback_request_str,
        )

        emit_event(
            "runner.completed",
            {
                "status": status,
                "completion_reason": completion_reason,
                "steps": len(steps),
                "handback_request": handback_request_str,
            },
        )

        html_logger.log_run_end(status, completion_reason)

        return result

    return _perform_run()

__all__ = ["runner"]
