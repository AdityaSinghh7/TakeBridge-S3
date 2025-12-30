"""Shared utility helpers for agent coordination and formatting."""

from __future__ import annotations

import logging
import re
import time
from io import BytesIO
from typing import Dict, Iterable, Optional, Tuple

from PIL import Image

from computer_use_agent.memory.procedural_memory import PROCEDURAL_MEMORY
from shared import agent_signal
from shared.streaming import (
    create_collector,
    emit_event,
    sanitize_event_name,
    streaming_enabled,
)

logger = logging.getLogger("desktopenv.agent")


def create_pyautogui_code(agent, code: str, obs: Dict) -> str:
    """
    Evaluate plan code into a grounded pyautogui snippet using the current observation.
    """
    agent.assign_screenshot(obs)
    exec_env = {"agent": agent}
    return eval(code, exec_env)


def call_llm_safe(
    agent,
    temperature: float = 0.0,
    use_thinking: bool = False,
    cost_source: Optional[str] = None,
    **kwargs,
) -> str:
    """Invoke an LMMAgent with basic retry and logging."""
    max_retries = 3
    attempt = 0
    response = ""
    kwargs = dict(kwargs)
    kwargs.pop("use_thinking", None)  # Ensure engines without support do not receive this flag
    event_base = sanitize_event_name(cost_source or "llm")
    last_collector = None
    model_name = getattr(getattr(agent, "engine", None), "model", None)

    while attempt < max_retries:
        try:
            agent_signal.raise_if_exit_requested()
            if agent_signal.is_paused():
                agent_signal.wait_for_resume()
            call_kwargs = dict(kwargs)
            collector = None
            attempt_index = attempt + 1
            if streaming_enabled() and cost_source:
                metadata = {"attempt": attempt_index}
                if model_name:
                    metadata["model"] = model_name
                collector = create_collector(cost_source, metadata=metadata)
                call_kwargs["stream"] = True
                call_kwargs["stream_handler"] = collector.handler
            if cost_source:
                emit_event(
                    f"{event_base}.started",
                    {
                        "attempt": attempt_index,
                        "temperature": temperature,
                        "use_thinking": use_thinking,
                    },
                )
            response = agent.get_response(
                temperature=temperature,
                cost_source=cost_source,
                **call_kwargs,
            )
            assert response is not None, "Response from agent should not be None"
            last_collector = collector
            logger.debug("LLM response succeeded on attempt %d", attempt + 1)
            break
        except Exception as exc:
            attempt += 1
            logger.warning("LLM call attempt %d failed: %s", attempt, exc)
            if attempt == max_retries:
                logger.error("Max retries reached while calling LLM.")
                if cost_source:
                    emit_event(
                        f"{event_base}.failed",
                        {"attempts": attempt, "error": str(exc)},
                    )
        agent_signal.sleep_with_interrupt(1.0)
    final_response = response if response is not None else ""
    if cost_source and final_response:
        attempts_used = attempt + 1
        answer, thoughts = split_thinking_response(final_response)
        payload = {
            "attempts": attempts_used,
            "text": final_response,
        }
        if model_name:
            payload["model"] = model_name
        if thoughts:
            payload["thoughts"] = thoughts
        if answer and answer != final_response:
            payload["answer"] = answer
        if last_collector:
            streamed_thoughts = last_collector.reasoning_text()
            streamed_output = last_collector.output_text()
            if streamed_thoughts and streamed_thoughts.strip():
                payload["streamed_thoughts"] = streamed_thoughts
            if streamed_output and streamed_output.strip():
                payload["streamed_output"] = streamed_output
        emit_event(f"{event_base}.completed", payload)
    return final_response


def call_llm_formatted(
    generator,
    format_checkers,
    *,
    cost_source: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Call an LMMAgent and enforce response formatting via formatter callbacks.
    """
    max_retries = 3
    attempt = 0
    response = ""
    messages = kwargs.pop("messages", generator.messages.copy())

    while attempt < max_retries:
        response = call_llm_safe(
            generator,
            messages=messages,
            cost_source=cost_source,
            **kwargs,
        )
        try:
            from computer_use_agent.utils.formatters import normalize_agent_action_response
        except Exception as exc:
            logger.debug("Agent response normalization unavailable: %s", exc)
        else:
            normalized_response, wrapped = normalize_agent_action_response(response)
            if wrapped:
                logger.info("Auto-wrapped unfenced agent action response.")
                response = normalized_response

        feedback_msgs = []
        for format_checker in format_checkers:
            success, feedback = format_checker(response)
            if not success:
                feedback_msgs.append(feedback)

        if not feedback_msgs:
            return response

        logger.error(
            "Response formatting error on attempt %d for %s: %s",
            attempt + 1,
            getattr(generator.engine, "model", "unknown"),
            response,
        )
        messages.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": response}],
            }
        )
        formatting_feedback = "- " + "\n- ".join(feedback_msgs)
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": PROCEDURAL_MEMORY.FORMATTING_FEEDBACK_PROMPT.replace(
                            "FORMATTING_FEEDBACK", formatting_feedback
                        ),
                    }
                ],
            }
        )
        logger.info("Provided formatting feedback:\n%s", formatting_feedback)
        attempt += 1

    logger.error("Failed to obtain correctly formatted response after retries.")
    return response


def split_thinking_response(full_response: str) -> Tuple[str, str]:
    try:
        thoughts = full_response.split("<thoughts>")[-1].split("</thoughts>")[0].strip()
        answer = full_response.split("<answer>")[-1].split("</answer>")[0].strip()
        return answer, thoughts
    except Exception:
        return full_response, ""


def parse_code_from_string(input_string: str) -> str:
    input_string = input_string.strip()
    pattern = r"```(?:\w+\s+)?(.*?)```"
    matches = re.findall(pattern, input_string, re.DOTALL)
    if not matches:
        return ""
    return matches[-1].strip()


def extract_agent_functions(code: str):
    pattern = r"(agent\.\w+\(\s*.*\))"
    return re.findall(pattern, code, re.DOTALL)


def compress_image(image_bytes: bytes = None, image: Image.Image = None) -> bytes:
    if not image:
        image = Image.open(BytesIO(image_bytes))
    output = BytesIO()
    image.save(output, format="WEBP")
    return output.getvalue()
