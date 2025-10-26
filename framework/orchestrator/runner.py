from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.agent_s import AgentS3
from framework.api.controller_client import VMControllerClient
from framework.grounding.grounding_agent import OSWorldACI
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
    controller = VMControllerClient(
        base_url=request.controller.base_url,
        host=request.controller.host,
        port=request.controller.port,
        timeout=request.controller.timeout,
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

    before_screenshot_bytes = controller.capture_screenshot()
    previous_behavior_result: Optional[Dict[str, Any]] = None

    for step_index in range(1, max_steps + 1):
        observation = {
            "screenshot": before_screenshot_bytes,
            "previous_behavior": previous_behavior_result,
        }

        info, actions = agent.predict(
            instruction=request.task, observation=observation
        )
        action = actions[0] if actions else ""
        exec_code = info.get("exec_code", action)

        execution_result: Dict[str, Any] = {}
        normalized = action.strip().upper()

        after_screenshot_bytes = before_screenshot_bytes

        if normalized == "DONE":
            status = "success"
            completion_reason = "DONE"
            after_screenshot_bytes = controller.capture_screenshot()
        elif normalized == "FAIL":
            status = "failed"
            completion_reason = "FAIL"
            after_screenshot_bytes = controller.capture_screenshot()
        elif normalized in {"WAIT", "WAIT;"} or action.strip().startswith("WAIT"):
            time.sleep(1.0)
            after_screenshot_bytes = controller.capture_screenshot()
        elif action.strip():
            execution_result = _execute_remote_pyautogui(controller, action)
            after_screenshot_bytes = controller.capture_screenshot()
        else:
            after_screenshot_bytes = controller.capture_screenshot()

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
                behavior_fact_thoughts=behavior.get("fact_thoughts"),
                behavior_fact_answer=behavior.get("fact_answer"),
            )
        )

        previous_behavior_result = behavior

        if normalized in {"DONE", "FAIL"}:
            break

        before_screenshot_bytes = after_screenshot_bytes
        time.sleep(0.5)

    else:
        status = "timeout"

    grounding_prompts = _build_grounding_prompts(
        grounding_cfg.grounding_system_prompt
    )

    return RunnerResult(
        task=request.task,
        status=status,
        completion_reason=completion_reason,
        steps=steps,
        grounding_prompts=grounding_prompts,
    )


__all__ = ["runner"]
