from __future__ import annotations

import base64
import copy
import json
import logging
import os
import textwrap
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from computer_use_agent.grounding.agent_tools import GroundingActionToolExecutor
from computer_use_agent.grounding.grounding_agent import OSWorldACI
from computer_use_agent.memory.procedural_memory import PROCEDURAL_MEMORY
from computer_use_agent.orchestrator.checkpointer import get_graph_checkpointer
from computer_use_agent.orchestrator.data_types import (
    OrchestrateRequest,
    RunnerResult,
    RunnerStep,
)
from computer_use_agent.orchestrator.graph_state import ComputerUseGraphState
from computer_use_agent.orchestrator.llm_adapter import ToolCallingLLMAdapter
from computer_use_agent.utils.behavior_narrator import BehaviorNarrator
from computer_use_agent.utils.common_utils import split_thinking_response
from computer_use_agent.utils.computer_use_html_logger import ComputerUseHtmlLogger
from computer_use_agent.utils.local_env import LocalEnv
from server.api.controller_client import VMControllerClient
from shared import agent_signal
from shared.db.workflow_runs import mark_run_attention, merge_agent_states
from shared.latency_logger import LATENCY_LOGGER
from shared.run_context import RUN_LOG_ID
from shared.streaming import emit_event

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
    script = code.strip()
    payload = base64.b64encode(script.encode("utf-8")).decode("utf-8")
    python_cmd_template = 'import base64; exec(base64.b64decode("{payload}").decode())'
    python_exe = "python3"
    try:
        platform_val = controller.get_platform()
        if isinstance(platform_val, str) and platform_val.lower().startswith("win"):
            python_exe = "python"
    except Exception:
        platform_val = None
    python_cmd = python_cmd_template.format(payload=payload)

    try:
        preview = script[:400].replace("\n", "\\n")
        logger.info(
            "Executing remote pyautogui via %s platform=%s preview=%s",
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
    keep_image_turns: int,
) -> List[Dict[str, Any]]:
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
            part_type = part.get("type")
            if part_type in {"image", "image_url"} and idx < total - keep_image_turns:
                continue
            new_content.append(part)
        msg_copy = dict(msg)
        msg_copy["content"] = new_content
        pruned.append(msg_copy)
    return pruned


def _build_trajectory_till_now(
    generator_messages: List[Dict[str, Any]],
    reflection_messages: List[Dict[str, Any]],
    *,
    code_agent_history: Optional[List[Dict[str, Any]]] = None,
    knowledge: Optional[List[str]] = None,
) -> Dict[str, Any]:
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
    snapshot: Dict[str, Any] = {
        "generator_messages": filtered_generator,
        "reflection_messages": filtered_reflection,
    }
    if isinstance(code_agent_history, list):
        snapshot["code_agent_history"] = copy.deepcopy(code_agent_history)
    if isinstance(knowledge, list):
        snapshot["knowledge"] = list(knowledge)
    return snapshot


def _build_trajectory_markdown(
    steps: List[RunnerStep],
    status: str,
    completion_reason: str,
    *,
    is_resume_flow: bool = False,
    handback_inference: Optional[Dict[str, Any]] = None,
    include_final_status: bool = True,
) -> str:
    lines: List[str] = []
    for step in steps:
        lines.append(f"## Step {step.step_index}")
        lines.append("")

        if step.plan:
            lines.append("### Worker Agent")
            lines.append(f"**Plan**: {step.plan}")
            if step.action:
                action_display = step.action
                if len(action_display) > 600:
                    action_display = action_display[:600] + "... (truncated)"
                lines.append(f"**Action**: `{action_display}`")
            if step.execution_result:
                result_json = json.dumps(step.execution_result, indent=2, ensure_ascii=False)
                lines.append(f"**Execution Result**:\n```json\n{result_json}\n```")

        if step.reflection:
            lines.append("")
            lines.append("### Reflection Agent")
            lines.append(f"**Reflection**: {step.reflection}")
            if step.reflection_thoughts:
                lines.append(f"**Thoughts**: {step.reflection_thoughts}")

        if step.behavior_fact_answer:
            lines.append("")
            lines.append("### Behaviour Narrator")
            lines.append(f"**Observation**: {step.behavior_fact_answer}")
            if step.behavior_fact_thoughts:
                lines.append(f"**Analysis**: {step.behavior_fact_thoughts}")

        if step.info:
            code_output = step.info.get("code_agent_output")
            if code_output:
                lines.append("")
                lines.append("### Code Agent")
                if isinstance(code_output, dict):
                    summary = code_output.get("summary", "")
                    completion = code_output.get("completion_reason", "")
                    exec_history = code_output.get("execution_history", [])
                    if summary:
                        lines.append(f"**Summary**: {summary}")
                    if completion:
                        lines.append(f"**Completion**: {completion}")
                    if exec_history:
                        lines.append("**Execution History**:")
                        for hist_step in exec_history:
                            step_num = hist_step.get("step", "?")
                            action = hist_step.get("action", "")
                            thoughts = hist_step.get("thoughts", "")
                            lines.append(f"  Step {step_num}:")
                            if action and action not in {"DONE", "FAIL"}:
                                lines.append(f"    **Code**: ```\n{action}\n```")
                            else:
                                lines.append(f"    **Action**: {action}")
                            if thoughts:
                                lines.append(f"    **Thoughts**: {thoughts[:400]}")

        if step.handback_request:
            lines.append("")
            lines.append("### Handback to Human")
            lines.append(f"**Request**: {step.handback_request}")
            lines.append("**Status**: Awaiting human intervention")

        lines.append("")

    if is_resume_flow:
        lines.append("## Resume Context")
        lines.append("This is a resume flow. A handback_to_human occurred in this step.")
        if handback_inference:
            inference_json = json.dumps(handback_inference, ensure_ascii=False, indent=2)
            lines.append("")
            lines.append("### Handback Inference")
            lines.append("The most recent handback result:")
            lines.append(f"```json\n{inference_json}\n```")
    elif include_final_status:
        lines.append("## Final Status")
        lines.append(f"**Status**: {status}")
        lines.append(f"**Completion Reason**: {completion_reason}")

    return "\n".join(lines)


def _guess_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _image_url_from_b64(image_b64: Optional[str]) -> Optional[str]:
    if not image_b64:
        return None
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        return None
    mime = _guess_image_mime(raw)
    return f"data:{mime};base64,{image_b64}"


def _tool_payload_from_messages(messages: List[Any]) -> Dict[str, Any]:
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue
        payload: Dict[str, Any]
        artifact = getattr(message, "artifact", None)
        if isinstance(artifact, dict):
            payload = dict(artifact)
            payload.setdefault("tool_name", getattr(message, "name", None))
            if getattr(message, "status", "success") == "error":
                payload.setdefault("status_signal", "FAIL")
                payload.setdefault("exec_code", "FAIL")
                payload.setdefault(
                    "execution_result",
                    {"error": str(message.content or "tool_error")},
                )
            return payload
        content = message.content
        if isinstance(content, dict):
            payload = dict(content)
        elif isinstance(content, list):
            joined = "\n".join(str(part) for part in content)
            try:
                payload = json.loads(joined)
            except Exception:
                payload = {"value": joined}
        else:
            text = str(content or "")
            try:
                payload = json.loads(text)
            except Exception:
                payload = {"value": text}
        payload.setdefault("tool_name", getattr(message, "name", None))
        if getattr(message, "status", "success") == "error":
            payload.setdefault("status_signal", "FAIL")
            payload.setdefault("exec_code", "FAIL")
            payload.setdefault("execution_result", {"error": str(content or "tool_error")})
        return payload
    return {}


def _tool_node_error_message(exc: Exception) -> str:
    payload = {
        "status_signal": "FAIL",
        "exec_code": "FAIL",
        "execution_result": {"error": str(exc)},
        "action_kind": "tool_error",
    }
    return json.dumps(payload, ensure_ascii=False)


def _format_code_agent_history(history: List[Dict[str, Any]]) -> str:
    if not history:
        return ""
    lines = ["", "CODE AGENT HISTORY:"]
    for idx, code_result in enumerate(history, 1):
        lines.append(f"Result {idx}:")
        lines.append(f"Task/Subtask Instruction: {code_result.get('task_instruction', '')}")
        lines.append(f"Steps Completed: {code_result.get('steps_executed', '')}")
        lines.append(f"Max Steps: {code_result.get('budget', '')}")
        lines.append(f"Completion Reason: {code_result.get('completion_reason', '')}")
        lines.append(f"Summary: {code_result.get('summary', '')}")
    lines.append("")
    return "\n".join(lines)


def _build_request_snapshot(request: OrchestrateRequest) -> Dict[str, Any]:
    return {
        "task": request.task,
        "worker": asdict(request.worker),
        "grounding": asdict(request.grounding),
        "controller": asdict(request.controller),
        "platform": request.platform,
        "enable_code_execution": request.enable_code_execution,
        "tool_constraints": asdict(request.tool_constraints) if request.tool_constraints else None,
    }


class _RunnerRuntime:
    def __init__(
        self,
        *,
        request: OrchestrateRequest,
        controller: VMControllerClient,
        platform: str,
        screen_width: int,
        screen_height: int,
        run_id: str,
    ) -> None:
        self.request = request
        self.controller = controller
        self.platform = platform
        self.run_id = run_id
        self.thread_id = run_id
        self.checkpoint_ns = "computer_use"
        self.worker_cfg = request.worker
        self.grounding_cfg = request.grounding
        self.html_logger = ComputerUseHtmlLogger(run_id)
        env = LocalEnv() if request.enable_code_execution else ControllerEnv(controller)

        self.grounding_agent = OSWorldACI(
            env=env,
            platform=platform,
            engine_params_for_generation=self.grounding_cfg.engine_params_for_generation,
            engine_params_for_grounding=self.grounding_cfg.engine_params_for_grounding,
            width=screen_width,
            height=screen_height,
            code_agent_budget=self.grounding_cfg.code_agent_budget,
            code_agent_engine_params=self.grounding_cfg.code_agent_engine_params,
            grounding_base_url=self.grounding_cfg.grounding_base_url,
            grounding_system_prompt=self.grounding_cfg.grounding_system_prompt,
            grounding_timeout=self.grounding_cfg.grounding_timeout,
            grounding_max_retries=self.grounding_cfg.grounding_max_retries,
            grounding_api_key=self.grounding_cfg.grounding_api_key,
        )
        self.behavior_narrator = BehaviorNarrator(engine_params=self.worker_cfg.engine_params)
        self.generator_adapter = ToolCallingLLMAdapter(self.worker_cfg.engine_params)
        self.reflection_adapter = ToolCallingLLMAdapter(self.worker_cfg.engine_params)
        self.tool_executor = GroundingActionToolExecutor(
            grounding_agent=self.grounding_agent,
            controller=self.controller,
            remote_execute_fn=_execute_remote_pyautogui,
            post_action_worker_delay=self.worker_cfg.post_action_worker_delay,
        )
        self.tools = self.tool_executor.build_tools()
        self.tool_node = ToolNode(
            self.tools,
            handle_tool_errors=_tool_node_error_message,
        )
        self.generator_prompt_template = self._load_generator_prompt_template()

    def _load_generator_prompt_template(self) -> str:
        prompt_path = Path("computer_use_agent/worker/system_prompt.txt")
        raw = _read_text_prompt(prompt_path).strip()
        if "Your response should be formatted like this:" in raw:
            raw = raw.split("Your response should be formatted like this:", 1)[0].rstrip()
        tool_block = ["Available tools you can call directly (one per step):"]
        for tool in self.tools:
            tool_block.append(f"- `{tool.name}`: {tool.description or ''}")
        raw = raw.replace("... agent actions inserted dynamically ...", "\n".join(tool_block))
        raw = raw.replace(
            "... connected actions section inserted dynamically ...",
            "",
        )
        raw = raw + textwrap.dedent(
            """

            ### Tool Calling Format
            - You must call exactly one tool each step.
            - Do not return code fences or pseudo-code.
            - If the task is completed, call `done`.
            - If the task is impossible, call `fail`.
            """
        )
        return raw.replace("CURRENT_OS", self.platform)

    def _fetch_apps_and_windows_info(self) -> str:
        try:
            apps_info = ""
            windows_info = ""
            try:
                apps_data = self.controller.get_apps(exclude_system=True)
                if isinstance(apps_data, dict) and apps_data.get("status") == "success":
                    app_names = apps_data.get("apps", [])
                    if app_names:
                        apps_info = (
                            f"\n4. Currently available apps ({len(app_names)} total): "
                            f"{', '.join(app_names)}"
                        )
            except Exception:
                logger.debug("Failed to fetch apps info", exc_info=True)
            try:
                windows_data = self.controller.get_active_windows(exclude_system=True)
                if isinstance(windows_data, dict) and windows_data.get("status") == "success":
                    windows = windows_data.get("windows", [])
                    if windows:
                        windows_info = (
                            "\n5. Currently active windows you can switch to if needed "
                            f"({len(windows)} total):"
                        )
                        for window in windows:
                            app_name = window.get("app_name") or window.get("title", "Unknown")
                            windows_info += f"\n   - {app_name}"
                    else:
                        windows_info = "\n5. Currently, no applications/windows are open."
            except Exception:
                logger.debug("Failed to fetch windows info", exc_info=True)
            return apps_info + windows_info
        except Exception:
            return ""

    def generator_system_prompt(self) -> str:
        prompt = self.generator_prompt_template
        apps_windows_info = self._fetch_apps_and_windows_info()
        placeholder = "... apps and windows information inserted dynamically ..."
        if placeholder in prompt:
            return prompt.replace(placeholder, apps_windows_info)
        if apps_windows_info:
            return prompt + "\n" + apps_windows_info
        return prompt


def _persist_handback_state(runtime: _RunnerRuntime, state: ComputerUseGraphState) -> None:
    run_id = runtime.run_id
    handback_request = state.get("handback_request")
    if not run_id or not handback_request:
        return

    steps = [RunnerStep(**step) for step in state.get("step_artifacts", [])]
    partial_trajectory_md = _build_trajectory_markdown(
        steps,
        status="attention",
        completion_reason="HANDOFF_TO_HUMAN",
        is_resume_flow=bool(state.get("is_resume_flow")),
        handback_inference=state.get("handback_inference_result"),
        include_final_status=False,
    )
    computer_use_snapshot = {
        "status": "attention",
        "completion_reason": "HANDOFF_TO_HUMAN",
        "step_index_next": state.get("step_index", 0) + 1,
        "checkpoint": {
            "thread_id": runtime.thread_id,
            "checkpoint_ns": runtime.checkpoint_ns,
        },
        "trajectory_till_now": _build_trajectory_till_now(
            state.get("generator_messages", []),
            state.get("reflection_messages", []),
            code_agent_history=state.get("code_agent_history"),
            knowledge=state.get("knowledge"),
        ),
        "runner": {
            "trajectory_md": partial_trajectory_md,
        },
        "handback_request": handback_request,
        "handback_screenshot_b64": (
            state.get("last_tool_result", {}) or {}
        ).get("after_screenshot_b64"),
        "request": _build_request_snapshot(runtime.request),
    }
    merge_agent_states(run_id, computer_use_snapshot, path=["agents", "computer_use"])
    if state.get("orchestrator_state"):
        merge_agent_states(run_id, {"orchestrator": state["orchestrator_state"]})
    mark_run_attention(run_id, summary=f"Human attention required: {handback_request[:200]}")
    emit_event(
        "human_attention.required",
        {
            "request": handback_request,
            "step_index": state.get("step_index"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
        },
    )


def _build_graph(runtime: _RunnerRuntime):
    def bootstrap(state: ComputerUseGraphState) -> ComputerUseGraphState:
        updates: ComputerUseGraphState = {}
        if not state.get("initialized"):
            initial_b64 = state.get("before_screenshot_b64")
            if not initial_b64:
                with LATENCY_LOGGER.measure("runner", "capture_screenshot", extra={"phase": "initial"}):
                    initial_b64 = base64.b64encode(
                        runtime.controller.capture_screenshot()
                    ).decode("utf-8")
            updates["before_screenshot_b64"] = initial_b64
            updates["reflection_screenshot_b64"] = (
                state.get("reflection_screenshot_b64") or initial_b64
            )
            updates["initialized"] = True
        if state.get("is_resume_flow") and state.get("status") == "attention":
            updates["status"] = "in_progress"
            updates["completion_reason"] = "MAX_STEPS_REACHED"
        return updates

    def reflector(state: ComputerUseGraphState) -> ComputerUseGraphState:
        current_step = int(state.get("step_index", 0)) + 1
        if not state.get("enable_reflection", True):
            emit_event("worker.reflection.skipped", {"step": current_step, "reason": "disabled"})
            return {"reflection": None, "reflection_thoughts": None}

        reflection_messages = list(state.get("reflection_messages", []) or [])
        screenshot_b64 = state.get("reflection_screenshot_b64") or state.get("before_screenshot_b64")
        image_url = _image_url_from_b64(screenshot_b64)

        if state.get("step_index", 0) == 0 and not reflection_messages:
            emit_event("worker.reflection.skipped", {"step": current_step, "reason": "initial_step"})
            return {"reflection": None, "reflection_thoughts": None}

        emit_event("worker.reflection.started", {"step": current_step})
        last_plan = state.get("plan") or ""
        history_block = _format_code_agent_history(state.get("code_agent_history", []))
        reflection_text = last_plan + history_block
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": reflection_text}]
        if image_url:
            user_content.append({"type": "image_url", "image_url": {"url": image_url, "detail": "high"}})
        user_msg = {"role": "user", "content": user_content}

        full_messages = [
            {"role": "system", "content": PROCEDURAL_MEMORY.REFLECTION_ON_TRAJECTORY},
            *reflection_messages,
            user_msg,
        ]
        response = runtime.reflection_adapter._client.create_response(  # noqa: SLF001
            messages=full_messages,
            reasoning_effort="low",
            reasoning_summary="auto",
            max_output_tokens=6500,
            cost_source="worker.reflection",
        )
        from shared.llm_client import extract_assistant_text

        full_reflection = extract_assistant_text(response) or ""
        raw = split_thinking_response(full_reflection)
        reflection, reflection_thoughts = raw
        reflection_messages.append(user_msg)
        reflection_messages.append(
            {"role": "assistant", "content": [{"type": "text", "text": full_reflection}]}
        )
        emit_event(
            "worker.reflection.summary",
            {"step": current_step, "reflection": reflection, "thoughts": reflection_thoughts},
        )
        return {
            "reflection_messages": _prune_images_in_messages(
                reflection_messages, keep_image_turns=int(state.get("max_trajectory_length", 1))
            ),
            "reflection": reflection,
            "reflection_thoughts": reflection_thoughts,
        }

    def next_step_generator(state: ComputerUseGraphState) -> ComputerUseGraphState:
        current_step = int(state.get("step_index", 0)) + 1
        emit_event("worker.step.started", {"step": current_step})

        runtime.grounding_agent.knowledge = list(state.get("knowledge", []) or [])
        runtime.grounding_agent.code_agent_history = list(state.get("code_agent_history", []) or [])
        runtime.grounding_agent.set_task_context(state.get("task", runtime.request.task))
        runtime.tool_executor.update_step_context(
            before_screenshot_b64=state.get("before_screenshot_b64"),
            step_index=current_step,
        )

        if state.get("step_index", 0) == 0 and not state.get("is_resume_flow"):
            generator_message = "The initial screen is provided. No action has been taken yet."
        else:
            generator_message = "The current state screenshot is provided below."

        reflection = state.get("reflection")
        if reflection:
            generator_message += (
                "\nREFLECTION: You may use this reflection on the previous action and overall trajectory:\n"
                f"{reflection}\n"
            )

        previous_behavior = state.get("previous_behavior") or {}
        if previous_behavior.get("fact_answer"):
            generator_message += (
                "\nBehavior Narrator — Previous Step Outcome\n"
                "Use this as an objective summary of visual changes from the last action.\n"
                f"{previous_behavior.get('fact_answer')}\n"
            )

        generator_message += f"\nCurrent Text Buffer = [{','.join(state.get('knowledge', []) or [])}]\n"
        history_block = _format_code_agent_history(state.get("code_agent_history", []) or [])
        if history_block:
            generator_message += history_block

        if state.get("pending_handback_inference"):
            generator_message += "\nHANDBACK TO HUMAN RESULT:\n"
            generator_message += f"{state['pending_handback_inference']}\n"
            generator_message += (
                "Use this information to understand what happened during the pause and continue accordingly.\n"
            )

        screenshot_b64 = state.get("before_screenshot_b64")
        image_url = _image_url_from_b64(screenshot_b64)
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": generator_message}]
        if image_url:
            user_content.append({"type": "image_url", "image_url": {"url": image_url, "detail": "high"}})
        user_msg = {"role": "user", "content": user_content}

        generator_messages = list(state.get("generator_messages", []) or [])
        full_messages = [
            {"role": "developer", "content": runtime.generator_system_prompt()},
            *generator_messages,
            user_msg,
        ]
        emit_event(
            "worker.generator.prompt_ready",
            {
                "step": current_step,
                "notes_count": len(state.get("knowledge", []) or []),
                "has_code_agent_context": bool(state.get("code_agent_history")),
            },
        )
        ai_message, _ = runtime.generator_adapter.generate_ai_message(
            messages=full_messages,
            tools=runtime.tools,
            reasoning_effort="medium",
            cost_source="worker.generator",
            max_output_tokens=6500,
        )
        plan = ai_message.content if isinstance(ai_message.content, str) else str(ai_message.content)
        assistant_payload = {"role": "assistant", "content": [{"type": "text", "text": plan}]}
        if ai_message.tool_calls:
            assistant_payload["tool_calls"] = ai_message.tool_calls
        generator_messages.append(user_msg)
        generator_messages.append(assistant_payload)
        emit_event(
            "worker.step.ready",
            {
                "step": current_step,
                "plan": plan,
                "reflection": state.get("reflection"),
                "reflection_thoughts": state.get("reflection_thoughts"),
            },
        )
        return {
            "plan": plan,
            "messages": [ai_message],
            "generator_messages": _prune_images_in_messages(
                generator_messages, keep_image_turns=int(state.get("max_trajectory_length", 1))
            ),
            "pending_handback_inference": None,
            "no_tool_retries": 0,
        }

    def generator_repair(state: ComputerUseGraphState) -> ComputerUseGraphState:
        retries = int(state.get("no_tool_retries", 0)) + 1
        if retries >= 3:
            return {
                "status": "failed",
                "completion_reason": "NO_TOOL_CALL",
                "no_tool_retries": retries,
            }
        repair_msg = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Invalid response: you must call exactly one tool in the next response. "
                        "Do not return plain text-only output."
                    ),
                }
            ],
        }
        generator_messages = list(state.get("generator_messages", []) or [])
        generator_messages.append(repair_msg)
        return {"generator_messages": generator_messages, "no_tool_retries": retries}

    def behavior_narrator(state: ComputerUseGraphState) -> ComputerUseGraphState:
        payload = _tool_payload_from_messages(state.get("messages", []))
        if not payload:
            payload = dict(state.get("last_tool_result", {}) or {})
        if not payload:
            return {"last_tool_result": {}}

        action = str(payload.get("exec_code") or "")
        status_signal = str(payload.get("status_signal") or "")
        before_b64 = payload.get("before_screenshot_b64")
        after_b64 = payload.get("after_screenshot_b64")
        behavior = None
        if status_signal != "HANDBACK" and before_b64 and after_b64:
            try:
                behavior = runtime.behavior_narrator.judge(
                    screenshot_num=int(state.get("step_index", 0)) + 1,
                    before_img_bytes=base64.b64decode(before_b64),
                    after_img_bytes=base64.b64decode(after_b64),
                    pyautogui_action=action,
                )
            except Exception:
                logger.warning("Behavior narrator failed for step=%s", state.get("step_index", 0) + 1, exc_info=True)
        return {"last_tool_result": payload, "behavior": behavior}

    def step_finalize(state: ComputerUseGraphState) -> ComputerUseGraphState:
        payload = dict(state.get("last_tool_result", {}) or {})
        if not payload:
            return {}
        next_step_index = int(state.get("step_index", 0)) + 1
        behavior = state.get("behavior") or {}
        behavior_artifacts = behavior.get("artifacts") if isinstance(behavior, dict) else None

        action = str(payload.get("exec_code") or "")
        status_signal = str(payload.get("status_signal") or "")
        info: Dict[str, Any] = {}
        if payload.get("code_agent_output") is not None:
            info["code_agent_output"] = payload.get("code_agent_output")

        step_record: Dict[str, Any] = {
            "step_index": next_step_index,
            "plan": state.get("plan", ""),
            "action": action,
            "exec_code": action,
            "execution_result": payload.get("execution_result") or {},
            "reflection": state.get("reflection"),
            "reflection_thoughts": state.get("reflection_thoughts"),
            "info": info,
            "behavior_fact_thoughts": behavior.get("fact_thoughts") if isinstance(behavior, dict) else None,
            "behavior_fact_answer": behavior.get("fact_answer") if isinstance(behavior, dict) else None,
            "action_kind": payload.get("action_kind", "gui"),
            "tool_name": payload.get("tool_name"),
            "tool_args": payload.get("args") or {},
            "status_signal": status_signal,
            "before_screenshot_b64": payload.get("before_screenshot_b64"),
            "after_screenshot_b64": payload.get("after_screenshot_b64"),
            "delayed_after_screenshot_b64": payload.get("delayed_after_screenshot_b64"),
            "raw_tool_payload": payload,
            "handback_request": payload.get("handback_request"),
            "handback_screenshot_b64": payload.get("after_screenshot_b64"),
        }

        step_artifacts = list(state.get("step_artifacts", []) or [])
        step_artifacts.append(step_record)

        next_before = payload.get("delayed_after_screenshot_b64") or payload.get("after_screenshot_b64")
        updates: ComputerUseGraphState = {
            "step_index": next_step_index,
            "step_artifacts": step_artifacts,
            "previous_behavior": behavior if isinstance(behavior, dict) else None,
            "before_screenshot_b64": next_before or state.get("before_screenshot_b64"),
            "reflection_screenshot_b64": next_before or state.get("reflection_screenshot_b64"),
            "knowledge": list(payload.get("knowledge") or state.get("knowledge", []) or []),
            "code_agent_history": list(
                payload.get("code_agent_history") or state.get("code_agent_history", []) or []
            ),
            "last_code_agent_result": payload.get("code_agent_output"),
            "last_action": action,
            "last_exec_code": action,
            "handback_request": payload.get("handback_request") or state.get("handback_request"),
            "behavior": None,
        }

        status = state.get("status", "in_progress")
        completion_reason = state.get("completion_reason", "MAX_STEPS_REACHED")
        if status_signal == "DONE":
            status = "success"
            completion_reason = "DONE"
        elif status_signal == "FAIL":
            status = "failed"
            completion_reason = "FAIL"
        elif status_signal == "HANDBACK":
            status = "attention"
            completion_reason = "HANDOFF_TO_HUMAN"
        updates["status"] = status
        updates["completion_reason"] = completion_reason

        emit_event(
            "runner.step.agent_response",
            {
                "step": next_step_index,
                "action": action,
                "exec_code": action,
                "normalized_action": status_signal,
                "info": info,
            },
        )
        emit_event(
            "runner.step.completed",
            {
                "step": next_step_index,
                "status": status,
                "action": action,
                "completion_reason": completion_reason if status != "in_progress" else None,
            },
        )
        emit_event(
            "runner.step.behavior",
            {
                "step": next_step_index,
                "fact_answer": step_record.get("behavior_fact_answer"),
                "fact_thoughts": step_record.get("behavior_fact_thoughts"),
            },
        )

        before_img = None
        after_img = None
        delayed_img = None
        try:
            if payload.get("before_screenshot_b64"):
                before_img = base64.b64decode(payload["before_screenshot_b64"])
            if payload.get("after_screenshot_b64"):
                after_img = base64.b64decode(payload["after_screenshot_b64"])
            if payload.get("delayed_after_screenshot_b64"):
                delayed_img = base64.b64decode(payload["delayed_after_screenshot_b64"])
        except Exception:
            pass
        runtime.html_logger.log_step(
            step_index=next_step_index,
            action=action,
            exec_code=action,
            execution_mode=str(payload.get("status_signal", "CONTINUE")).lower(),
            status=status,
            completion_reason=completion_reason if status != "in_progress" else None,
            plan=state.get("plan"),
            reflection=state.get("reflection"),
            handback_request=payload.get("handback_request"),
            behavior_fact=step_record.get("behavior_fact_answer"),
            behavior_thoughts=step_record.get("behavior_fact_thoughts"),
            before_img=before_img,
            after_img=after_img,
            delayed_after_img=delayed_img if delayed_img != after_img else None,
            marked_before_img=(behavior_artifacts or {}).get("marked_before_img_bytes"),
            marked_after_img=(behavior_artifacts or {}).get("marked_after_img_bytes"),
            zoomed_after_img=(behavior_artifacts or {}).get("zoomed_after_img_bytes"),
        )
        return updates

    def termination_gate(state: ComputerUseGraphState) -> ComputerUseGraphState:
        updates: ComputerUseGraphState = {}
        if state.get("status") == "in_progress" and int(state.get("step_index", 0)) >= int(
            state.get("max_steps", runtime.worker_cfg.max_steps)
        ):
            updates["status"] = "timeout"
            updates["completion_reason"] = "MAX_STEPS_REACHED"
        if (updates.get("status") or state.get("status")) == "attention":
            _persist_handback_state(runtime, {**state, **updates})
        return updates

    def finalize_result(state: ComputerUseGraphState) -> ComputerUseGraphState:
        steps = [RunnerStep(**step) for step in state.get("step_artifacts", [])]
        trajectory_md = _build_trajectory_markdown(
            steps,
            state.get("status", "in_progress"),
            state.get("completion_reason", "MAX_STEPS_REACHED"),
            is_resume_flow=bool(state.get("is_resume_flow")),
            handback_inference=state.get("handback_inference_result"),
        )
        grounding_prompts = _build_grounding_prompts(runtime.grounding_cfg.grounding_system_prompt)
        runtime.html_logger.log_run_end(
            state.get("status", "in_progress"),
            state.get("completion_reason", "MAX_STEPS_REACHED"),
        )
        emit_event(
            "runner.completed",
            {
                "status": state.get("status", "in_progress"),
                "completion_reason": state.get("completion_reason", "MAX_STEPS_REACHED"),
                "steps": len(steps),
                "handback_request": state.get("handback_request"),
            },
        )
        return {"trajectory_md": trajectory_md, "grounding_prompts": grounding_prompts}

    def route_after_generator(state: ComputerUseGraphState) -> str:
        messages = state.get("messages", [])
        if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
            return "tool_execution"
        return "generator_repair"

    def route_after_generator_repair(state: ComputerUseGraphState) -> str:
        if state.get("status") in {"failed", "timeout"}:
            return "finalize_result"
        return "next_step_generator"

    def route_after_termination(state: ComputerUseGraphState) -> str:
        if state.get("status") in {"success", "failed", "attention", "timeout"}:
            return "finalize_result"
        return "reflector"

    builder = StateGraph(ComputerUseGraphState)
    builder.add_node("bootstrap", bootstrap)
    builder.add_node("reflector", reflector)
    builder.add_node("next_step_generator", next_step_generator)
    builder.add_node("generator_repair", generator_repair)
    builder.add_node("tool_execution", runtime.tool_node)
    builder.add_node("behavior_narrator", behavior_narrator)
    builder.add_node("step_finalize", step_finalize)
    builder.add_node("termination_gate", termination_gate)
    builder.add_node("finalize_result", finalize_result)

    builder.add_edge(START, "bootstrap")
    builder.add_edge("bootstrap", "reflector")
    builder.add_edge("reflector", "next_step_generator")
    builder.add_conditional_edges(
        "next_step_generator",
        route_after_generator,
        {
            "tool_execution": "tool_execution",
            "generator_repair": "generator_repair",
        },
    )
    builder.add_conditional_edges(
        "generator_repair",
        route_after_generator_repair,
        {
            "next_step_generator": "next_step_generator",
            "finalize_result": "finalize_result",
        },
    )
    builder.add_edge("tool_execution", "behavior_narrator")
    builder.add_edge("behavior_narrator", "step_finalize")
    builder.add_edge("step_finalize", "termination_gate")
    builder.add_conditional_edges(
        "termination_gate",
        route_after_termination,
        {
            "reflector": "reflector",
            "finalize_result": "finalize_result",
        },
    )
    builder.add_edge("finalize_result", END)
    return builder.compile(checkpointer=get_graph_checkpointer())


def _initial_state_from_request(
    request: OrchestrateRequest,
    *,
    run_id: str,
    platform: str,
    orchestrator_context: Optional[Dict[str, Any]],
) -> ComputerUseGraphState:
    inference_update = (orchestrator_context or {}).get("inference_update") or {}
    handback_inference_context = (orchestrator_context or {}).get("handback_inference_context")
    is_resume_flow = bool((orchestrator_context or {}).get("is_resume_flow"))

    generator_messages: List[Dict[str, Any]] = []
    reflection_messages: List[Dict[str, Any]] = []
    knowledge: List[str] = []
    code_agent_history: List[Dict[str, Any]] = []
    before_screenshot_b64 = inference_update.get("latest_screenshot_b64")
    handback_inference_result = inference_update.get("inference_result")
    trajectory_state = inference_update.get("trajectory_till_now") or {}

    if isinstance(trajectory_state, dict):
        if isinstance(trajectory_state.get("generator_messages"), list):
            generator_messages = copy.deepcopy(trajectory_state.get("generator_messages") or [])
        if isinstance(trajectory_state.get("reflection_messages"), list):
            reflection_messages = copy.deepcopy(trajectory_state.get("reflection_messages") or [])
        if isinstance(trajectory_state.get("knowledge"), list):
            knowledge = list(trajectory_state.get("knowledge") or [])
        if isinstance(trajectory_state.get("code_agent_history"), list):
            code_agent_history = copy.deepcopy(trajectory_state.get("code_agent_history") or [])

    pending_handback_inference = handback_inference_context
    if not pending_handback_inference and handback_inference_result:
        pending_handback_inference = json.dumps(handback_inference_result, ensure_ascii=False)

    return {
        "messages": [],
        "task": request.task,
        "platform": platform,
        "max_steps": request.worker.max_steps,
        "max_trajectory_length": request.worker.max_trajectory_length,
        "enable_reflection": request.worker.enable_reflection,
        "post_action_worker_delay": request.worker.post_action_worker_delay,
        "is_resume_flow": is_resume_flow,
        "run_id": run_id,
        "orchestrator_state": (orchestrator_context or {}).get("orchestrator_state"),
        "initialized": False,
        "step_index": 0,
        "status": "in_progress",
        "completion_reason": "MAX_STEPS_REACHED",
        "no_tool_retries": 0,
        "generator_messages": generator_messages,
        "reflection_messages": reflection_messages,
        "reflection": None,
        "reflection_thoughts": None,
        "plan": "",
        "before_screenshot_b64": before_screenshot_b64,
        "reflection_screenshot_b64": before_screenshot_b64,
        "previous_behavior": None,
        "behavior": None,
        "knowledge": knowledge,
        "code_agent_history": code_agent_history,
        "last_code_agent_result": None,
        "pending_handback_inference": pending_handback_inference,
        "handback_inference_result": handback_inference_result,
        "last_tool_result": {},
        "last_action": "",
        "last_exec_code": "",
        "handback_request": None,
        "step_artifacts": [],
        "grounding_prompts": {},
        "trajectory_md": "",
    }


def runner(
    request: OrchestrateRequest,
    orchestrator_context: Optional[Dict[str, Any]] = None,
) -> RunnerResult:
    """Execute the computer-use agent as a LangGraph finite state machine."""

    agent_signal.clear_signal_state()
    controller = VMControllerClient(
        base_url=request.controller.base_url,
        host=request.controller.host,
        port=request.controller.port,
        timeout=request.controller.timeout,
    )
    controller.wait_for_health()

    try:
        screen_info = controller.screen_size()
        screen_width = int(screen_info.get("width", 1920))
        screen_height = int(screen_info.get("height", 1080))
    except Exception:
        screen_width, screen_height = 1920, 1080

    platform = (request.platform or controller.get_platform() or "unknown").lower()
    run_id = RUN_LOG_ID.get() or os.getenv("RUN_LOG_ID") or str(uuid.uuid4())
    inferred_thread_id = (
        ((orchestrator_context or {}).get("inference_update") or {})
        .get("checkpoint", {})
        .get("thread_id")
    )
    if inferred_thread_id:
        run_id = str(inferred_thread_id)
    runtime = _RunnerRuntime(
        request=request,
        controller=controller,
        platform=platform,
        screen_width=screen_width,
        screen_height=screen_height,
        run_id=run_id,
    )
    inferred_checkpoint_ns = (
        ((orchestrator_context or {}).get("inference_update") or {})
        .get("checkpoint", {})
        .get("checkpoint_ns")
    )
    if inferred_checkpoint_ns:
        runtime.checkpoint_ns = str(inferred_checkpoint_ns)

    emit_event(
        "runner.started",
        {"task": request.task, "max_steps": request.worker.max_steps, "platform": platform},
    )
    runtime.html_logger.log_run_start(request.task, platform)

    graph = _build_graph(runtime)
    initial_state = _initial_state_from_request(
        request,
        run_id=run_id,
        platform=platform,
        orchestrator_context=orchestrator_context,
    )
    config = {
        "configurable": {
            "thread_id": run_id,
            "checkpoint_ns": runtime.checkpoint_ns,
        }
    }
    final_state = cast(ComputerUseGraphState, graph.invoke(initial_state, config=config))

    steps = [RunnerStep(**step) for step in final_state.get("step_artifacts", [])]
    handback_request = final_state.get("handback_request")
    result = RunnerResult(
        task=request.task,
        status=final_state.get("status", "in_progress"),
        completion_reason=final_state.get("completion_reason", "MAX_STEPS_REACHED"),
        steps=steps,
        grounding_prompts=final_state.get("grounding_prompts", {}),
        trajectory_md=final_state.get("trajectory_md", ""),
        handback_request=handback_request,
        checkpoint={
            "thread_id": run_id,
            "checkpoint_ns": runtime.checkpoint_ns,
        },
    )
    return result


__all__ = ["runner"]
