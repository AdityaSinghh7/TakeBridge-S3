from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ComputerUseGraphState(TypedDict, total=False):
    # LangGraph-managed message channel used by ToolNode.
    messages: Annotated[List[BaseMessage], add_messages]

    # Request/runtime metadata.
    task: str
    platform: str
    max_steps: int
    max_trajectory_length: int
    enable_reflection: bool
    post_action_worker_delay: float
    is_resume_flow: bool
    run_id: Optional[str]
    orchestrator_state: Optional[Dict[str, Any]]

    # Execution status.
    initialized: bool
    step_index: int
    status: str
    completion_reason: str
    no_tool_retries: int

    # Worker/reflection histories.
    generator_messages: List[Dict[str, Any]]
    reflection_messages: List[Dict[str, Any]]
    reflection: Optional[str]
    reflection_thoughts: Optional[str]
    plan: str

    # Screenshots and behavior context.
    before_screenshot_b64: Optional[str]
    reflection_screenshot_b64: Optional[str]
    previous_behavior: Optional[Dict[str, Any]]
    behavior: Optional[Dict[str, Any]]

    # Knowledge/code-agent continuity.
    knowledge: List[str]
    code_agent_history: List[Dict[str, Any]]
    last_code_agent_result: Optional[Dict[str, Any]]
    pending_handback_inference: Optional[str]
    handback_inference_result: Optional[Dict[str, Any]]

    # Tool execution details.
    last_tool_result: Dict[str, Any]
    last_action: str
    last_exec_code: str
    handback_request: Optional[str]

    # Structured step artifacts for final rendering.
    step_artifacts: List[Dict[str, Any]]

    # Finalization payload.
    grounding_prompts: Dict[str, Any]
    trajectory_md: str

