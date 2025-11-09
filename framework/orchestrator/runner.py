from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.agent_s import AgentS3
from framework.api.controller_client import VMControllerClient
from framework.grounding.grounding_agent import OSWorldACI
# Ensure MCP actions register onto the ACI before Worker builds prompts
from framework.mcp import actions as mcp_actions  # noqa: F401
from framework.mcp.actions import configure_mcp_action_filters
from framework.mcp.mcp_agent import MCPAgent
from framework.orchestrator.data_types import (
    DEFAULT_CONTROLLER_CONFIG,
    DEFAULT_GROUNDING_CONFIG,
    DEFAULT_WORKER_CONFIG,
    OrchestrateRequest,
    RunnerResult,
    RunnerStep,
)
from framework.utils.local_env import LocalEnv
from framework.utils.behavior_narrator import BehaviorNarrator
from framework.utils.latency_logger import LATENCY_LOGGER
from framework.utils.streaming import emit_event
from framework.utils import agent_signal

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
    python_cmd = (
        "import base64, sys\n"
        "exec(base64.b64decode('{payload}').decode('utf-8'))"
    ).format(payload=payload)
    return controller.execute(["python3", "-c", python_cmd])


def _build_grounding_prompts(
    grounding_system_prompt: Optional[str],
) -> Dict[str, Any]:
    text_span_path = Path("framework/grounding/text_span_prompt.txt")
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


def runner(request: OrchestrateRequest) -> RunnerResult:
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
    tool_constraints = request.tool_constraints
    revert_action_filter = False
    if tool_constraints and tool_constraints.mode == "custom":
        configure_mcp_action_filters(
            tool_constraints.providers,
            tool_constraints.tools,
        )
        revert_action_filter = True
    else:
        configure_mcp_action_filters(None, None)
    emit_event(
        "runner.tools.configured",
        {
            "mode": (tool_constraints.mode if tool_constraints else "auto"),
            "providers": (tool_constraints.providers if tool_constraints else None),
            "tools": (tool_constraints.tools if tool_constraints else None),
        },
    )

    def _perform_run() -> RunnerResult:
        mcp_agent = MCPAgent()
        MCPAgent.set_current(mcp_agent)

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

        info: Dict[str, Any] = {"action_kind": "gui"}
        for step_index in range(1, max_steps + 1):
            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()

            mcp_agent.set_step(step_index)

            emit_event(
                "runner.step.started",
                {
                    "step": step_index,
                },
            )

            action_kind = info.get("action_kind", "gui")

            observation = {
                "screenshot": before_screenshot_bytes,
                "previous_behavior": previous_behavior_result,
                "reflection_screenshot": reflection_screenshot_bytes,
                "last_action_kind": action_kind,
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

            behavior = None
            if action_kind != "mcp":
                with LATENCY_LOGGER.measure("runner", "behavior_narrator", extra={"step": step_index}):
                    behavior = behavior_narrator.judge(
                        screenshot_num=step_index,
                        before_img_bytes=before_screenshot_bytes,
                        after_img_bytes=after_screenshot_bytes,
                        pyautogui_action=action,
                    )
            else:
                emit_event(
                    "runner.behavior.skipped",
                    {"step": step_index, "reason": "mcp_action"},
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
                    action_kind=action_kind,
                )
            )

            previous_behavior_result = behavior if action_kind != "mcp" else None

            mcp_agent.finalize_step()

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

        result = RunnerResult(
            task=request.task,
            status=status,
            completion_reason=completion_reason,
            steps=steps,
            grounding_prompts=grounding_prompts,
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

    try:
        return _perform_run()
    finally:
        if revert_action_filter:
            configure_mcp_action_filters(None, None)

__all__ = ["runner"]
