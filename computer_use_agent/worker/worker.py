import inspect
import json
from functools import partial
import logging
import os
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import base64
import copy

from computer_use_agent.grounding.grounding_agent import ACI
from computer_use_agent.core.module import BaseModule
from computer_use_agent.memory.procedural_memory import PROCEDURAL_MEMORY
from computer_use_agent.utils.common_utils import (
    call_llm_safe,
    call_llm_formatted,
    parse_code_from_string,
    split_thinking_response,
    create_pyautogui_code,
)
from computer_use_agent.utils.formatters import (
    SINGLE_ACTION_FORMATTER,
    CODE_VALID_FORMATTER,
    CALL_CODE_AGENT_SUBTASK_REQUIRED_FORMATTER,
)
from shared.streaming import emit_event
from shared.text_utils import safe_ascii
from shared.hierarchical_logger import (
    get_hierarchical_logger,
    get_step_id,
)

logger = logging.getLogger("desktopenv.agent")


class Worker(BaseModule):
    _SYSTEM_PROMPT_PATH = Path(__file__).with_name("system_prompt.txt")
    @staticmethod
    def _has_action_flag(method, flag: str) -> bool:
        if not method:
            return False
        if getattr(method, flag, False):
            return True
        func = getattr(method, "__func__", None)
        if func and getattr(func, flag, False):
            return True
        return False

    @classmethod
    def _load_system_prompt(
        cls,
        agent_class: type,
        skipped_actions: List[str],
    ) -> str:
        """Load the worker system prompt and inject dynamic GUI actions.

        - GUI actions: methods marked with `is_agent_action` on the grounding agent class.
        """
        if not cls._SYSTEM_PROMPT_PATH.exists():
            raise FileNotFoundError(
                f"Worker system prompt file not found at {cls._SYSTEM_PROMPT_PATH}"
            )

        base_prompt = cls._SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        # Build GUI action stubs
        action_lines: List[str] = []
        for attr_name in sorted(dir(agent_class)):
            if attr_name in skipped_actions:
                continue

            attr = getattr(agent_class, attr_name)
            if callable(attr) and getattr(attr, "is_agent_action", False):
                signature = inspect.signature(attr)
                docstring = inspect.getdoc(attr) or ""
                if docstring:
                    indented_doc = textwrap.indent(docstring, "        ")
                    docstring_block = f'        """\n{indented_doc}\n        """\n'
                else:
                    docstring_block = "        pass\n"
                action_lines.append(
                    f"    def {attr_name}{signature}:\n{docstring_block}\n"
                )

        actions_block = "".join(action_lines).rstrip() or "    pass"
        placeholder = "... agent actions inserted dynamically ..."
        if placeholder in base_prompt:
            prompt = base_prompt.replace(placeholder, f"\n{actions_block}\n")
        else:
            prompt = f"{base_prompt.rstrip()}\n{actions_block}"

        # Remove connected actions placeholder if it exists
        connected_placeholder = "... connected actions section inserted dynamically ..."
        if connected_placeholder in prompt:
            prompt = prompt.replace(connected_placeholder, "")

        return prompt.strip()

    def __init__(
        self,
        worker_engine_params: Dict,
        grounding_agent: ACI,
        platform: str = "ubuntu",
        max_trajectory_length: int = 8,
        enable_reflection: bool = True,
    ):
        """
        Worker receives the main task and generates actions, without the need of hierarchical planning
        Args:
            worker_engine_params: Dict
                Parameters for the worker agent
            grounding_agent: Agent
                The grounding agent to use
            platform: str
                OS platform the agent runs on (darwin, linux, windows)
            max_trajectory_length: int
                The amount of images turns to keep
            enable_reflection: bool
                Whether to enable reflection
        """
        super().__init__(worker_engine_params, platform)

        self.temperature = self.engine_params.get("temperature", 0.0)
        self.use_thinking = self.engine_params.get("model", "") in [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-sonnet-4-5-20250929",
        ]
        self.grounding_agent = grounding_agent
        self.max_trajectory_length = max_trajectory_length
        self.enable_reflection = enable_reflection

        self.reset()

    def reset(self):
        if self.platform != "linux":
            skipped_actions = ["set_cell_values"]
        else:
            skipped_actions = []

        # Hide code agent action entirely if no env/controller is available
        if not getattr(self.grounding_agent, "env", None) or not getattr(
            getattr(self.grounding_agent, "env", None), "controller", None
        ):
            skipped_actions.append("call_code_agent")

        sys_prompt = self._load_system_prompt(
            type(self.grounding_agent),
            skipped_actions=skipped_actions,
        ).replace("CURRENT_OS", self.platform)

        self.generator_agent = self._create_agent(sys_prompt)
        self.reflection_agent = self._create_agent(
            PROCEDURAL_MEMORY.REFLECTION_ON_TRAJECTORY
        )

        self.turn_count = 0
        self.worker_history = []
        self.reflections = []
        self.cost_this_turn = 0
        self.screenshot_inputs = []
        self.latest_gui_screenshot = None

    def _extract_response_field(self, payload: Any, key: str) -> Any:
        if isinstance(payload, dict):
            if key in payload:
                return payload[key]
            for value in payload.values():
                result = self._extract_response_field(value, key)
                if result is not None:
                    return result
        elif isinstance(payload, list):
            for item in payload:
                result = self._extract_response_field(item, key)
                if result is not None:
                    return result
        return None

    def _agent_has_image(self, agent) -> bool:
        if not agent or not getattr(agent, "messages", None):
            return False
        for msg in agent.messages:
            for part in msg.get("content", []):
                if part.get("type") == "image":
                    return True
        return False

    def _clear_fallback_image(self, agent) -> None:
        if not agent or not getattr(agent, "messages", None):
            return
        messages = agent.messages
        idx = 0
        while idx < len(messages):
            msg = messages[idx]
            content = msg.get("content", [])
            new_content = [
                part for part in content if not part.get("fallback_image")
            ]
            if len(new_content) != len(content):
                if new_content:
                    msg["content"] = new_content
                    idx += 1
                else:
                    messages.pop(idx)
            else:
                idx += 1
    def update_latest_screenshot(self, screenshot: bytes | None) -> None:
        if not screenshot:
            return
        self.latest_gui_screenshot = screenshot
        self._clear_fallback_image(self.generator_agent)
        self._clear_fallback_image(self.reflection_agent)

    def _ensure_image_context(self) -> None:
        if not self.latest_gui_screenshot:
            return
        for agent in (self.generator_agent, self.reflection_agent):
            if not agent:
                continue
            if self._agent_has_image(agent):
                continue
            self._clear_fallback_image(agent)
            agent.messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Reference screenshot for continuity (no new GUI action).",
                            "fallback_image": True,
                        },
                        {
                            "type": "image",
                            "image": self.latest_gui_screenshot,
                            "fallback_image": True,
                        },
                    ],
                }
            )

    def flush_messages(self):
        """Flush messages based on the model's context limits.

        This method ensures that the agent's message history does not exceed the maximum trajectory length.

        Side Effects:
            - Modifies the messages of generator, reflection, and bon_judge agents to fit within the context limits.
        """
        engine_type = self.engine_params.get("engine_type", "")

        # Flush strategy for long-context models: keep all text, only keep latest images
        if engine_type in ["anthropic", "openai", "gemini"]:
            max_images = self.max_trajectory_length
            for agent in [self.generator_agent, self.reflection_agent]:
                if agent is None:
                    continue
                # keep latest k images
                img_count = 0
                for i in range(len(agent.messages) - 1, -1, -1):
                    for j in range(len(agent.messages[i]["content"])):
                        if "image" in agent.messages[i]["content"][j].get("type", ""):
                            img_count += 1
                            if img_count > max_images:
                                del agent.messages[i]["content"][j]
                                break

        # Flush strategy for non-long-context models: drop full turns
        else:
            # generator msgs are alternating [user, assistant], so 2 per round
            if len(self.generator_agent.messages) > 2 * self.max_trajectory_length + 1:
                self.generator_agent.messages.pop(1)
                self.generator_agent.messages.pop(1)
            # reflector msgs are all [(user text, user image)], so 1 per round
            if len(self.reflection_agent.messages) > self.max_trajectory_length + 1:
                self.reflection_agent.messages.pop(1)

        # Prune prior "Current Text Buffer" lines from generator history, keeping only the latest user-message occurrence
        try:
            messages = getattr(self.generator_agent, "messages", []) or []
            kept_latest_user = False
            # Walk newest -> oldest so first match is the one we keep
            for idx in range(len(messages) - 1, -1, -1):
                msg = messages[idx]
                content = msg.get("content", [])
                role = msg.get("role", "")
                for part in content:
                    if part.get("type") == "text":
                        text = part.get("text", "")
                        if "Current Text Buffer =" in text:
                            lines = text.splitlines()
                            new_lines = []
                            removed_any = False
                            for line in lines:
                                if line.strip().startswith("Current Text Buffer ="):
                                    if role == "user" and not kept_latest_user:
                                        # Keep only the newest user message's buffer line
                                        kept_latest_user = True
                                        new_lines.append(line)
                                    else:
                                        # Drop buffer line from assistant messages or older user messages
                                        removed_any = True
                                else:
                                    new_lines.append(line)
                            if removed_any:
                                part["text"] = "\n".join(new_lines)
        except Exception:
            # Be conservative if anything goes wrong; don't block flushing
            pass
        self._ensure_image_context()

    def rehydrate_from_prompts(self, prompts_state: Dict[str, Any]) -> None:
        """
        Restore generator/reflection messages and latest screenshot from persisted state.
        """
        if not prompts_state or not isinstance(prompts_state, dict):
            return
        try:
            gen_state = prompts_state.get("generator", {}) or {}
            ref_state = prompts_state.get("reflection", {}) or {}

            gen_msgs = gen_state.get("messages")
            ref_msgs = ref_state.get("messages")

            # Deep copy to avoid mutating stored state
            if isinstance(gen_msgs, list):
                self.generator_agent.messages = copy.deepcopy(gen_msgs)
            if isinstance(ref_msgs, list):
                self.reflection_agent.messages = copy.deepcopy(ref_msgs)

            # Restore latest screenshot if provided
            latest_b64 = (
                gen_state.get("latest_gui_screenshot_b64")
                or ref_state.get("latest_gui_screenshot_b64")
            )
            if latest_b64:
                try:
                    self.latest_gui_screenshot = base64.b64decode(latest_b64)
                except Exception:
                    self.latest_gui_screenshot = None

            # Restore knowledge and code agent result if present
            if "knowledge" in prompts_state and isinstance(prompts_state.get("knowledge"), list):
                self.grounding_agent.knowledge = prompts_state.get("knowledge") or []
            if prompts_state.get("last_code_agent_result") is not None:
                self.grounding_agent.last_code_agent_result = prompts_state.get("last_code_agent_result")

            # Ensure images are not re-added by fallback
            self.flush_messages()
        except Exception as exc:
            logger.warning("Failed to rehydrate prompts: %s", exc)

    def _generate_reflection(self, instruction: str, obs: Dict) -> Tuple[str, str]:
        """
        Generate a reflection based on the current observation and instruction.

        Args:
            instruction (str): The task instruction.
            obs (Dict): The current observation containing the screenshot.

        Returns:
            Optional[str, str]: The generated reflection text and thoughts, if any (turn_count > 0).

        Side Effects:
            - Updates reflection agent's history
            - Generates reflection response with API call
        """
        reflection = None
        reflection_thoughts = None
        current_step = self.turn_count + 1
        if not self.enable_reflection:
            emit_event(
                "worker.reflection.skipped",
                {
                    "step": current_step,
                    "reason": "disabled",
                },
            )
            return reflection, reflection_thoughts
        if self.enable_reflection:
            # Load the initial message
            if self.turn_count == 0:
                image_bytes = obs.get("reflection_screenshot") or obs.get("screenshot")
                text_content = textwrap.dedent(
                    f"""
                    Task Description: {instruction}
                    Current Trajectory below:
                    """
                )
                updated_sys_prompt = (
                    self.reflection_agent.system_prompt + "\n" + text_content
                )
                self.reflection_agent.add_system_prompt(updated_sys_prompt)
                if image_bytes:
                    self.update_latest_screenshot(image_bytes)
                self.reflection_agent.add_message(
                    text_content="The initial screen is provided. No action has been taken yet.",
                    image_content=image_bytes,
                    role="user",
                )
                emit_event(
                    "worker.reflection.skipped",
                    {
                        "step": current_step,
                        "reason": "initial_step",
                    },
                )
            # Load the latest action
            else:
                image_bytes = obs.get("reflection_screenshot") or obs.get("screenshot")
                emit_event(
                    "worker.reflection.started",
                    {
                        "step": current_step,
                    },
                )
                reflection_text = self.worker_history[-1]
                if image_bytes:
                    self.update_latest_screenshot(image_bytes)
                self.reflection_agent.add_message(
                    text_content=reflection_text,
                    image_content=image_bytes,
                    role="user",
                )
                full_reflection = call_llm_safe(
                    self.reflection_agent,
                    temperature=self.temperature,
                    use_thinking=self.use_thinking,
                    reasoning_effort="low",
                    reasoning_summary="auto",
                    max_output_tokens=6500,
                    cost_source="worker.reflection",
                )
                reflection, reflection_thoughts = split_thinking_response(
                    full_reflection
                )
                self.reflections.append(reflection)
                logger.info("REFLECTION THOUGHTS: %s", reflection_thoughts)
                logger.info("REFLECTION: %s", reflection)
        if reflection or reflection_thoughts:
            emit_event(
                "worker.reflection.summary",
                {
                    "step": current_step,
                    "reflection": reflection,
                    "thoughts": reflection_thoughts,
                },
            )
        return reflection, reflection_thoughts

    def _fetch_apps_and_windows_info(self) -> str:
        """Fetch current apps and windows information from the server API."""
        try:
            controller = getattr(
                getattr(self.grounding_agent, "env", None), "controller", None
            )
            if not controller:
                logger.warning("Controller unavailable, skipping apps/windows info")
                return ""

            apps_info = ""
            windows_info = ""
            
            try:
                apps_data = controller.get_apps(exclude_system=True)
                if isinstance(apps_data, dict):
                    if apps_data.get("status") == "success":
                        app_names = apps_data.get("apps", [])
                        if app_names:
                            apps_info = (
                                f"\n4. Currently available apps ({len(app_names)} total): "
                                f"{', '.join(app_names)}"
                            )
                    else:
                        logger.warning(
                            "Apps API returned non-success status: %s",
                            apps_data.get("status"),
                        )
                else:
                    logger.warning("Unexpected /apps response: %s", apps_data)
            except Exception as e:
                logger.warning(f"Failed to fetch apps: {e}", exc_info=True)
            
            try:
                windows_data = controller.get_active_windows(exclude_system=True)
                if isinstance(windows_data, dict):
                    if windows_data.get("status") == "success":
                        windows = windows_data.get("windows", [])
                        if windows:
                            windows_info = (
                                "\n5. Currently active windows you can switch to if needed "
                                f"({len(windows)} total):"
                            )
                            for window in windows:
                                app_name = window.get("app_name") or window.get(
                                    "title", "Unknown"
                                )
                                windows_info += f"\n   - {app_name}"
                        else:
                            logger.info("Active windows API returned zero windows.")
                            windows_info = "\n5. Currently, no applications/windows are open."
                    else:
                        logger.warning(
                            "Windows API returned non-success status: %s",
                            windows_data.get("status"),
                        )
                else:
                    logger.warning("Unexpected /active_windows response: %s", windows_data)
            except Exception as e:
                logger.warning(f"Failed to fetch windows: {e}", exc_info=True)
            
            return apps_info + windows_info
            
        except Exception as e:
            logger.warning(f"Error fetching apps/windows info: {e}")
            return ""

    def generate_next_action(self, instruction: str, obs: Dict) -> Tuple[Dict, List]:
        """
        Predict the next action(s) based on the current observation.
        """

        current_step = self.turn_count + 1

        # Get hierarchical logger if available
        h_logger = get_hierarchical_logger()
        step_id = get_step_id() or "cu-main"
        worker_logger = None
        if h_logger:
            cu_logger = h_logger.get_agent_logger("computer_use", step_id)
            worker_logger = cu_logger.get_sub_logger("worker")
            worker_logger.log_event("step.started", {
                "step": current_step,
                "turn_count": self.turn_count,
            })

        emit_event(
            "worker.step.started",
            {
                "step": current_step,
            },
        )

        self.grounding_agent.assign_screenshot(obs)
        self.grounding_agent.set_task_context(instruction)
        previous_behavior = obs.get("previous_behavior")

        if self.turn_count > 0:
            generator_message = ""
        elif getattr(self, "resume_mode", False):
            generator_message = "The current state screenshot is provided below."
        else:
            generator_message = "The initial screen is provided. No action has been taken yet."

        # Load the task into the system prompt
        if self.turn_count == 0:
            prompt_with_instructions = self.generator_agent.system_prompt.replace(
                "TASK_DESCRIPTION", instruction
            )
            self.generator_agent.add_system_prompt(prompt_with_instructions)

        # Get the per-step reflection
        reflection, reflection_thoughts = self._generate_reflection(instruction, obs)
        if reflection:
            generator_message += f"REFLECTION: You may use this reflection on the previous action and overall trajectory:\n{reflection}\n"
        if previous_behavior and previous_behavior.get("fact_answer"):
            generator_message += (
                "\nBehavior Narrator — Previous Step Outcome\n"
                "Use this as an objective summary of visual changes from the last action. "
                "Treat it as high-signal evidence to verify success/failure and guide your next step; "
                "if anything conflicts, trust the current screenshot.\n"
                f"{previous_behavior['fact_answer']}\n"
            )

        # Get the grounding agent's knowledge base buffer
        generator_message += (
            f"\nCurrent Text Buffer = [{','.join(self.grounding_agent.knowledge)}]\n"
        )

        # Add code agent result from previous step if available (from full task or subtask execution)
        if (
            hasattr(self.grounding_agent, "last_code_agent_result")
            and self.grounding_agent.last_code_agent_result is not None
        ):
            code_result = self.grounding_agent.last_code_agent_result
            generator_message += f"\nCODE AGENT RESULT:\n"
            generator_message += (
                f"Task/Subtask Instruction: {code_result['task_instruction']}\n"
            )
            generator_message += f"Steps Completed: {code_result['steps_executed']}\n"
            generator_message += f"Max Steps: {code_result['budget']}\n"
            generator_message += (
                f"Completion Reason: {code_result['completion_reason']}\n"
            )
            generator_message += f"Summary: {code_result['summary']}\n"
            if code_result["execution_history"]:
                generator_message += f"Execution History:\n"
                for i, step in enumerate(code_result["execution_history"]):
                    action = step["action"]
                    # Format code snippets with proper backticks
                    if "```python" in action:
                        # Extract Python code and format it
                        code_start = action.find("```python") + 9
                        code_end = action.find("```", code_start)
                        if code_end != -1:
                            python_code = action[code_start:code_end].strip()
                            generator_message += (
                                f"Step {i+1}: \n```python\n{python_code}\n```\n"
                            )
                        else:
                            generator_message += f"Step {i+1}: \n{action}\n"
                    elif "```bash" in action:
                        # Extract Bash code and format it
                        code_start = action.find("```bash") + 7
                        code_end = action.find("```", code_start)
                        if code_end != -1:
                            bash_code = action[code_start:code_end].strip()
                            generator_message += (
                                f"Step {i+1}: \n```bash\n{bash_code}\n```\n"
                            )
                        else:
                            generator_message += f"Step {i+1}: \n{action}\n"
                    else:
                        generator_message += f"Step {i+1}: \n{action}\n"
            generator_message += "\n"

            # Save code agent result to text file
            try:
                import os
                from datetime import datetime

                # Create logs directory if it doesn't exist
                logs_dir = "logs"
                if not os.path.exists(logs_dir):
                    os.makedirs(logs_dir)

                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = (
                    f"logs/code_agent_result_step_{self.turn_count + 1}_{timestamp}.txt"
                )

                with open(
                    filename, "w", encoding="utf-8", errors="backslashreplace"
                ) as f:
                    f.write(f"CODE AGENT RESULT - Step {self.turn_count + 1}\n")
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    f.write(
                        f"Task/Subtask Instruction: {code_result['task_instruction']}\n"
                    )
                    f.write(f"Steps Completed: {code_result['steps_executed']}\n")
                    f.write(f"Max Steps: {code_result['budget']}\n")
                    f.write(f"Completion Reason: {code_result['completion_reason']}\n")
                    f.write(f"Summary: {code_result['summary']}\n")
                    if code_result["execution_history"]:
                        f.write(f"\nExecution History:\n")
                        for i, step in enumerate(code_result["execution_history"]):
                            f.write(f"\nStep {i+1}:\n")
                            f.write(f"Action: {step['action']}\n")
                            if "thoughts" in step:
                                f.write(f"Thoughts: {step['thoughts']}\n")

                logger.info(f"Code agent result saved to: {filename}")
            except Exception as e:
                logger.error(f"Failed to save code agent result to file: {e}")

            # Log the code agent result section for debugging (truncated execution history)
            log_message = f"\nCODE AGENT RESULT:\n"
            log_message += (
                f"Task/Subtask Instruction: {code_result['task_instruction']}\n"
            )
            log_message += f"Steps Completed: {code_result['steps_executed']}\n"
            log_message += f"Max Steps: {code_result['budget']}\n"
            log_message += f"Completion Reason: {code_result['completion_reason']}\n"
            log_message += f"Summary: {code_result['summary']}\n"
            if code_result["execution_history"]:
                log_message += f"Execution History (truncated):\n"
                # Only log first 3 steps and last 2 steps to keep logs manageable
                total_steps = len(code_result["execution_history"])
                for i, step in enumerate(code_result["execution_history"]):
                    if i < 3 or i >= total_steps - 2:  # First 3 and last 2 steps
                        action = step["action"]
                        if "```python" in action:
                            code_start = action.find("```python") + 9
                            code_end = action.find("```", code_start)
                            if code_end != -1:
                                python_code = action[code_start:code_end].strip()
                                log_message += (
                                    f"Step {i+1}: ```python\n{python_code}\n```\n"
                                )
                            else:
                                log_message += f"Step {i+1}: {action}\n"
                        elif "```bash" in action:
                            code_start = action.find("```bash") + 7
                            code_end = action.find("```", code_start)
                            if code_end != -1:
                                bash_code = action[code_start:code_end].strip()
                                log_message += (
                                    f"Step {i+1}: ```bash\n{bash_code}\n```\n"
                                )
                            else:
                                log_message += f"Step {i+1}: {action}\n"
                        else:
                            log_message += f"Step {i+1}: {action}\n"
                    elif i == 3 and total_steps > 5:
                        log_message += f"... (truncated {total_steps - 5} steps) ...\n"

            logger.info(
                "WORKER_CODE_AGENT_RESULT_SECTION - Step %s: Code agent result added to generator message:\n%s",
                self.turn_count + 1,
                safe_ascii(log_message),
            )

            # Reset the code agent result after adding it to context
            self.grounding_agent.last_code_agent_result = None

        # Add handback inference result if present (from human intervention)
        if (
            hasattr(self.grounding_agent, "handback_inference")
            and self.grounding_agent.handback_inference is not None
        ):
            handback_inference = self.grounding_agent.handback_inference
            generator_message += "\nHANDBACK TO HUMAN RESULT:\n"
            generator_message += (
                f"You previously requested human intervention and the run was paused.\n"
            )
            generator_message += f"{handback_inference}\n"
            generator_message += (
                "Use this information to understand what happened during the pause "
                "and continue with the task accordingly.\n"
            )
            logger.info(
                f"WORKER_HANDBACK_RESULT - Step {self.turn_count + 1}: Handback inference added to generator message"
            )
            # Reset the handback inference after adding it to context
            self.grounding_agent.handback_inference = None

        # Update system prompt with current apps and windows information
        apps_windows_info = self._fetch_apps_and_windows_info()
        if apps_windows_info:
            # Get current system prompt
            current_sys_prompt = self.generator_agent.system_prompt
            placeholder = "... apps and windows information inserted dynamically ..."
            
            # Check if placeholder exists (first turn) or if apps/windows section already exists (subsequent turns)
            if placeholder in current_sys_prompt:
                # First turn: replace placeholder
                updated_sys_prompt = current_sys_prompt.replace(placeholder, apps_windows_info)
                self.generator_agent.add_system_prompt(updated_sys_prompt)
            elif "Currently available apps" in current_sys_prompt:
                # Subsequent turns: replace existing apps/windows section
                # Pattern to match the apps/windows section (from "4. Currently available apps" to just before "### END OF GUIDELINES")
                pattern = r'\n4\. Currently available apps.*?(?=\n### END OF GUIDELINES|$)'
                match = re.search(pattern, current_sys_prompt, re.DOTALL)
                if match:
                    # Replace the existing section
                    updated_sys_prompt = (
                        current_sys_prompt[:match.start()] + 
                        apps_windows_info + 
                        current_sys_prompt[match.end():]
                    )
                    self.generator_agent.add_system_prompt(updated_sys_prompt)
                else:
                    # Fallback: insert before "### END OF GUIDELINES"
                    end_guidelines_start = current_sys_prompt.find("### END OF GUIDELINES")
                    if end_guidelines_start != -1:
                        updated_sys_prompt = (
                            current_sys_prompt[:end_guidelines_start] + 
                            apps_windows_info + "\n\n" +
                            current_sys_prompt[end_guidelines_start:]
                        )
                        self.generator_agent.add_system_prompt(updated_sys_prompt)
                    else:
                        logger.warning("Could not find insertion point for apps/windows info in system prompt")
            else:
                # If neither placeholder nor existing section found, insert before "### END OF GUIDELINES"
                end_guidelines_start = current_sys_prompt.find("### END OF GUIDELINES")
                if end_guidelines_start != -1:
                    updated_sys_prompt = (
                        current_sys_prompt[:end_guidelines_start] + 
                        apps_windows_info + "\n\n" +
                        current_sys_prompt[end_guidelines_start:]
                    )
                    self.generator_agent.add_system_prompt(updated_sys_prompt)
                else:
                    logger.warning("Could not find insertion point for apps/windows info in system prompt")

        # Finalize the generator message
        screenshot_bytes = obs.get("screenshot")
        if screenshot_bytes:
            self.update_latest_screenshot(screenshot_bytes)
        self.generator_agent.add_message(
            generator_message, image_content=screenshot_bytes, role="user"
        )
        emit_event(
            "worker.generator.prompt_ready",
            {
                "step": current_step,
                "notes_count": len(getattr(self.grounding_agent, "knowledge", []) or []),
                "has_code_agent_context": bool(
                    hasattr(self.grounding_agent, "last_code_agent_result")
                    and self.grounding_agent.last_code_agent_result
                ),
            },
        )

        # Generate the plan and next action
        format_checkers = [
            SINGLE_ACTION_FORMATTER,
            CALL_CODE_AGENT_SUBTASK_REQUIRED_FORMATTER,
            partial(CODE_VALID_FORMATTER, self.grounding_agent, obs),
        ]
        plan = call_llm_formatted(
            self.generator_agent,
            format_checkers,
            temperature=self.temperature,
            use_thinking=self.use_thinking,
            reasoning_effort="medium",
            reasoning_summary="auto",
            max_output_tokens=6500,
            cost_source="worker.generator",
        )
        self.worker_history.append(plan)
        self.generator_agent.add_message(plan, role="assistant")
        logger.info("PLAN:\n %s", plan)

        # Extract the next action from the plan
        plan_code = parse_code_from_string(plan)
        try:
            assert plan_code, "Plan code should not be empty"
            exec_code = create_pyautogui_code(self.grounding_agent, plan_code, obs)
        except Exception as e:
            logger.error(
                f"Could not evaluate the following plan code:\n{plan_code}\nError: {e}"
            )
            exec_code = self.grounding_agent.wait(
                1.333
            )  # Skip a turn if the code cannot be evaluated

        executor_info = {
            "plan": plan,
            "plan_code": plan_code,
            "exec_code": exec_code,
            "reflection": reflection,
            "reflection_thoughts": reflection_thoughts,
            "code_agent_output": (
                self.grounding_agent.last_code_agent_result
                if hasattr(self.grounding_agent, "last_code_agent_result")
                and self.grounding_agent.last_code_agent_result is not None
                else None
            ),
            "previous_behavior_thoughts": previous_behavior.get("fact_thoughts")
            if previous_behavior
            else None,
            "previous_behavior_answer": previous_behavior.get("fact_answer")
            if previous_behavior
            else None,
        }
        emit_event(
            "worker.step.ready",
            {
                "step": current_step,
                "plan": plan,
                "plan_code": plan_code,
                "exec_code": exec_code,
                "reflection": reflection,
                "reflection_thoughts": reflection_thoughts,
                "previous_behavior_thoughts": executor_info["previous_behavior_thoughts"],
                "previous_behavior_answer": executor_info["previous_behavior_answer"],
            },
        )

        # Log step completion to hierarchical logger
        if worker_logger:
            worker_logger.log_event("step.completed", {
                "step": current_step,
                "plan": plan,
                "has_reflection": reflection is not None,
                "has_code_agent_output": executor_info.get("code_agent_output") is not None,
            })

        self.turn_count += 1
        self.screenshot_inputs.append(
            obs.get("reflection_screenshot") or obs.get("screenshot")
        )
        self.flush_messages()
        return executor_info, [exec_code]
