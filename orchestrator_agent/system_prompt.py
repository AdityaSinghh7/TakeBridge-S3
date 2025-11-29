"""
System prompt for the orchestrator agent.

This module provides a dynamic system prompt builder that incorporates:
1. Static foundation (role, routing principles, guidelines)
2. Dynamic capabilities (MCP providers, desktop environment)
3. Multi-step context (previous results, budget status)

Keeping this as Python makes it easy to import and attach to downstream
planner/agent calls without reading from disk.
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator_agent.data_types import OrchestratorRequest, RunState, StepResult

STATIC_FOUNDATION = """\
You are the Orchestrator Agent - a meta-agent that decides the next atomic step to accomplish a user's task.

## Your Role

You analyze the user's goal, review what has been accomplished so far, and decide the **single next step** to execute. After each step completes, you will be called again to decide the next action.

## Available Agents

### MCP Agent
**When to use:**
- API-accessible operations (email, messaging, CRM, database queries, file storage)
- Data retrieval and manipulation via APIs
- Tool-based automation with OAuth-connected services
- Structured data operations (search, create, update, delete via APIs)

**What MCP returns:**
- Structured API responses (JSON data, lists, objects)
- Success/failure status from API calls
- Data retrieved from services (emails, messages, records, files)
- Confirmation of actions taken (email sent, record created, etc.)

**Capabilities:** See provider list below
**Strengths:** Fast, reliable, precise, works with APIs
**Limitations:** Cannot handle UI, visual elements, or desktop applications

**How to formulate tasks for MCP:**
Be specific to help the agent discover the right tools quickly:
- ✅ "Use Gmail provider's gmail_search tool to find emails from john@example.com in the last 7 days"
- ✅ "Use Slack provider's slack_post_message tool to send 'Meeting at 3pm' to #general channel"
- ✅ "Use Shopify provider's shopify_get_order tool to retrieve details for order #12345"
- ❌ "Search for emails" (too vague - which provider? what search criteria?)
- ❌ "Send a message" (unclear - Slack? Email? Which tool?)

**Template:** "Use [provider] provider's [probable_tool] tool to [specific action with parameters]"

### Computer-Use Agent
**When to use:**
- Desktop application automation (Excel, PowerPoint, native apps)
- UI interactions requiring visual grounding
- Multi-application workflows on desktop
- Any task requiring human-like interaction with a desktop interface

**Available GUI Actions:**
- **click** - Click on UI elements (buttons, links, icons, etc.)
- **type** - Type text into input fields, text areas, or documents
- **scroll** - Scroll within windows or elements (up/down/left/right)
- **drag_and_drop** - Drag items from one location to another
- **highlight_text_span** - Select/highlight text using OCR
- **hotkey** - Press keyboard shortcuts (Ctrl+C, Cmd+V, etc.)
- **open** - Open applications or files via system launcher
- **switch_applications** - Switch between open application windows
- **wait** - Pause execution for a specified duration
- **call_code_agent** - Execute code-based subtasks (spreadsheet formulas, data processing)
- **save_to_knowledge** - Store information for later use in the task

**What Computer-Use returns:**
- Descriptions of UI actions taken (clicked "Submit button", typed "hello@example.com")
- Screenshots and visual observations
- Confirmation of operations (file downloaded, app opened, text highlighted)
- Extracted information from visual elements via OCR

**Capabilities:** See desktop environment below
**Strengths:** Can handle any desktop UI, visual understanding, platform-aware
**Limitations:** Slower than API calls, less robust than MCP due to grounding errors

**How to formulate tasks for Computer-Use:**
- Be specific about UI elements: "Click the blue 'Submit' button in the bottom-right corner"
- Specify exact text to type: "Type 'john@example.com' into the email field"
- Describe visual locations clearly: "Scroll down in the main content area"
- Mention application context: "In Excel, click the 'Insert Chart' button"

## Decision Framework

**Choose the right agent:**
1. **If the task can be done via an available API provider** → Use MCP
2. **If the task requires desktop UI interaction** → Use Computer-Use
3. **If you're unsure which provider/app can help** → Use MCP first to search/explore, then decide next step

**Examples:**

**MCP Tasks (with proper formulation):**
- ✅ "Use Gmail provider's gmail_send_email tool to send email to john@example.com with subject 'Meeting Notes' and body 'See attached'"
- ✅ "Use Slack provider's slack_search_messages tool to find messages in #engineering channel from the last 24 hours"
- ✅ "Use Shopify provider's shopify_update_order tool to add tag 'returned' to order #12345"
- ✅ "Use Google Drive provider's drive_upload_file tool to upload the invoice.pdf file to the 'Invoices' folder"

**Computer-Use Tasks (with proper formulation):**
- ✅ "Open Excel application, then click the blue 'Submit' button in the bottom-right corner of the spreadsheet"
- ✅ "In the Chrome browser, click on the 'Download Invoice' button, then wait 5 seconds for download to complete"
- ✅ "Type 'Q4 Revenue Report' into the filename input field at the top of the document"
- ✅ "Use hotkey Ctrl+C to copy the selected text, then switch to Notepad and use Ctrl+V to paste"

**Hybrid Workflows:**
- Step 1 (Computer-Use): "Open Chrome and navigate to the 3PL portal, click 'Download Invoice' button"
- Step 2 (Computer-Use): "Wait 5 seconds for invoice.pdf to download to the Downloads folder"
- Step 3 (MCP): "Use Google Drive provider's drive_upload_file tool to upload ~/Downloads/invoice.pdf to 'Invoices' folder"

## Understanding Previous Steps

When reviewing previous step results, interpret them based on the agent used:

**MCP Agent Results:**
- Look for API response data (emails found, records created, files uploaded)
- Check for tool outputs (list of items, confirmation messages, retrieved data)
- Errors typically indicate API failures (unauthorized, not found, rate limit)

**Computer-Use Agent Results:**
- Look for UI action descriptions (clicked X, typed Y, navigated to Z)
- Check for visual observations (saw button, found text, window opened)
- Errors typically indicate UI issues (element not found, app crashed, timeout)

## Your Output Format

Respond with JSON in **ONE** of these three formats:

### 1. Next Step (most common)
{
  "type": "next_step",
  "target": "mcp" | "computer_use",
  "task": "Clear, specific description of what this step should accomplish",
  "reasoning": "Brief explanation of why this is the right next step"
}

### 2. Task Complete
{
  "type": "task_complete",
  "reasoning": "Explanation of how the user's original goal has been fully accomplished"
}

### 3. Task Impossible
{
  "type": "task_impossible",
  "reasoning": "Clear explanation of why the task cannot be completed (missing capabilities, stuck in loop, fundamental blocker)"
}

**Important Guidelines:**
- Output exactly ONE of the three response types above
- Use `task_impossible` if you detect a loop (same action failing repeatedly)
- Use `task_impossible` if required capabilities are not available
- Use `task_complete` only when the original user goal is fully satisfied

**Task Formulation Requirements:**

For MCP tasks:
- ✅ ALWAYS mention the provider name (Gmail, Slack, Shopify, etc.)
- ✅ ALWAYS suggest the probable tool name (gmail_search, slack_post_message, etc.)
- ✅ ALWAYS include specific parameters (email address, channel name, order ID, etc.)
- ✅ Use template: "Use [provider] provider's [tool_name] tool to [action with params]"
- ❌ NEVER be vague ("search for emails" - specify which provider and search criteria)

For Computer-Use tasks:
- ✅ ALWAYS describe UI elements in detail ("the blue 'Submit' button in the bottom-right corner")
- ✅ ALWAYS specify exact text to type ("Type 'john@example.com' into the email field")
- ✅ ALWAYS mention the application context ("In Excel, click the 'Insert Chart' button")
- ✅ ALWAYS be specific about visual locations ("Scroll down in the main content area")
- ❌ NEVER be vague ("click the button" - specify which button, where it is, what it looks like)
"""


CAPABILITY_TEMPLATE = """
## Current Capabilities

### MCP Providers (API/Tool-based automation)
{mcp_providers}

### Desktop Environment (UI automation)
**Platform:** {platform}
**Available Applications:** {available_apps}
**Active Windows:**
{active_windows}
"""


CONTEXT_TEMPLATE = """
## Current Task

**User's Goal:** {task}

**Steps Completed So Far:**
{previous_results}
"""


FAILURE_REMINDER = """
## ⚠️ Previous Step Failed

**Last Action:** {failed_task} (via {failed_target} agent)
**Error:** {failed_error}

**What to do next:**
- Analyze if this failure blocks the entire task or if there's an alternative approach
- If you can work around it, output the next step to try (different approach, different agent, etc.)
- If this failure makes the task impossible, output `task_impossible` with clear reasoning
- If you've seen this same error multiple times, the task is likely impossible
"""


def format_mcp_providers(providers: List[Dict[str, Any]]) -> str:
    """
    Format MCP provider tree for prompt readability.

    Args:
        providers: List of provider dicts with 'provider' and 'tools' keys

    Returns:
        Formatted string listing providers and their tools
    """
    if not providers:
        return "⚠️  No MCP providers authorized. User needs to connect OAuth accounts."

    lines = []
    for p in providers:
        tool_list = ", ".join(p["tools"][:5])  # Show first 5 tools
        if len(p["tools"]) > 5:
            tool_list += f", ... ({len(p['tools'])} tools total)"
        lines.append(f"- **{p['provider']}**: {tool_list}")

    return "\n".join(lines)


def format_desktop_environment(
    apps: List[str], windows: List[Dict[str, Any]]
) -> tuple[str, str]:
    """
    Format desktop apps and windows for prompt.

    Args:
        apps: List of application names
        windows: List of window dicts with 'app_name' and 'title' keys

    Returns:
        Tuple of (formatted_apps, formatted_windows) strings
    """
    apps_str = ", ".join(apps) if apps else "No applications detected"

    if not windows:
        windows_str = "No active windows"
    else:
        windows_lines = []
        for w in windows[:10]:  # Limit to 10 windows
            app_name = w.get("app_name", "Unknown")
            title = w.get("title", "")
            windows_lines.append(f"  - {app_name}: \"{title}\"")

        windows_str = "\n".join(windows_lines)
        if len(windows) > 10:
            windows_str += f"\n  ... ({len(windows) - 10} more windows)"

    return apps_str, windows_str


def _render_json(value: Any, max_chars: int = 4000) -> str:
    """
    Pretty-print JSON-like objects with optional truncation to control token use.

    Args:
        value: Any serializable object
        max_chars: Maximum characters to return before truncating (0/None to disable).
                  This limit applies per call (i.e., per key/value we render), not to
                  the entire multi-key structure.

    Returns:
        String representation suitable for inclusion in prompts
    """
    try:
        text = json.dumps(value, indent=4, ensure_ascii=False)
    except Exception:
        text = str(value)

    if max_chars and len(text) > max_chars:
        return f"{text[:max_chars]}... (+{len(text) - max_chars} chars truncated)"
    return text


def format_previous_results(
    results: List["StepResult"], task: Optional[str] = None
) -> str:
    """
    Format previous step results for context using translator output as the single
    source of truth. Presents a clean, structured view with no truncation of
    translator-derived content.

    Args:
        results: List of StepResult objects
        task: Optional task string for additional context when no results exist

    Returns:
        Formatted string showing recent step outcomes with retrieved data
    """
    if not results:
        return (
            f"None - this is the first step for task: {task}"
            if task
            else "None - this is the first step."
        )

    lines = []
    for i, r in enumerate(results, 1):  # Show all steps with numbering
        output = r.output or {}
        translated = output.get("translated", {})

        overall_success = translated.get("overall_success")
        success_flag = overall_success if isinstance(overall_success, bool) else bool(r.success)
        total_steps = translated.get("total_steps")
        steps_summary = translated.get("steps_summary") or []
        data_block = translated.get("data")
        artifacts = translated.get("artifacts") or {}
        error_text = translated.get("error") or r.error
        summary = translated.get("summary") or output.get("summary") or "No summary"

        header = f"### {r.target.upper()} step – Task: {r.next_task}"
        status_line = f"Overall result: {'Completed' if success_flag else 'Failed'}"
        run_length_line = f"Agent reported total steps: {total_steps if total_steps is not None else 'unknown'}"

        step_lines = [f"{i}. {header}", f"   {status_line}", f"   {run_length_line}", f"   Summary: {summary}"]

        if steps_summary:
            step_lines.append("   Stepwise summary:")
            for entry in steps_summary:
                step_lines.append(f"     - {entry}")
        else:
            step_lines.append("   Stepwise summary: not provided")

        if data_block and isinstance(data_block, dict):
            step_lines.append("   Data:")
            for key, value in list(data_block.items())[:5]:
                value_str = _render_json(value, max_chars=None)
                step_lines.append(f"     - {key}: {value_str}")
            if len(data_block) > 5:
                step_lines.append(f"     ... ({len(data_block) - 5} more)")

        # Artifacts
        tool_calls = artifacts.get("tool_calls") or []
        search_results = artifacts.get("search_results") or []
        ui_observations = artifacts.get("ui_observations") or []
        code_executions = artifacts.get("code_executions") or []

        if any([tool_calls, search_results, ui_observations, code_executions]):
            step_lines.append("   Artifacts:")

        if tool_calls:
            step_lines.append(f"     Tool calls ({len(tool_calls)}):")
            for call in tool_calls[:5]:
                tool_id = call.get("tool_id", "unknown")
                call_status = call.get("success")
                status_label = (
                    "success" if call_status is True else "fail" if call_status is False else "unknown"
                )
                args_str = _render_json(call.get("arguments"), max_chars=None)
                resp_str = _render_json(call.get("response"), max_chars=None)
                step_lines.append(f"       - {tool_id} ({status_label})")
                step_lines.append(f"         arguments: {args_str}")
                step_lines.append(f"         response: {resp_str}")
            if len(tool_calls) > 5:
                step_lines.append(f"       ... ({len(tool_calls) - 5} more)")

        if search_results:
            step_lines.append(f"     Search results ({len(search_results)}):")
            for sr in search_results[:5]:
                query = sr.get("query", "")
                count = sr.get("tools_found")
                tool_names = sr.get("tool_names") or []
                count_text = count if count is not None else len(tool_names)
                step_lines.append(f"       - query: {query} | tools_found: {count_text} | tool_names: {', '.join(tool_names)}")
            if len(search_results) > 5:
                step_lines.append(f"       ... ({len(search_results) - 5} more)")

        if ui_observations:
            step_lines.append(f"     UI observations ({len(ui_observations)}):")
            for obs in ui_observations[:5]:
                obs_str = _render_json(obs, max_chars=None)
                step_lines.append(f"       - {obs_str}")
            if len(ui_observations) > 5:
                step_lines.append(f"       ... ({len(ui_observations) - 5} more)")

        if code_executions:
            step_lines.append(f"     Code executions ({len(code_executions)}):")
            for exec_entry in code_executions[:5]:
                code_str = _render_json(exec_entry.get("code"), max_chars=None)
                output_str = _render_json(exec_entry.get("output"), max_chars=None)
                exec_status = exec_entry.get("success")
                exec_label = (
                    "success" if exec_status is True else "fail" if exec_status is False else "unknown"
                )
                step_lines.append(f"       - {exec_label}")
                step_lines.append(f"         code: {code_str}")
                step_lines.append(f"         output: {output_str}")
            if len(code_executions) > 5:
                step_lines.append(f"       ... ({len(code_executions) - 5} more)")

        if error_text:
            step_lines.append(f"   Error: {error_text}")

        # Provide a full translated JSON block for downstream planners
        if translated:
            full_json = _render_json(translated, max_chars=None)
            indented = "\n".join(f"     {line}" for line in full_json.splitlines())
            step_lines.append("   Full translated payload:")
            step_lines.append(indented)

        lines.append("\n".join(step_lines))

    return "\n\n".join(lines)


def build_system_prompt(
    request: "OrchestratorRequest",
    capabilities: Dict[str, Any],
    state: Optional["RunState"] = None,
    last_step_failed: bool = False,
    failed_step_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build dynamic system prompt with capabilities and context.

    Args:
        request: The orchestration request
        capabilities: Output from build_capability_context()
        state: Current run state (for multi-turn context)
        last_step_failed: Whether the last step failed
        failed_step_info: Info about the failed step if last_step_failed=True

    Returns:
        Complete system prompt string
    """
    # Start with static foundation
    prompt_parts = [STATIC_FOUNDATION]

    # Add capability context
    mcp_caps = capabilities.get("mcp", {})
    computer_caps = capabilities.get("computer", {})

    mcp_providers_str = format_mcp_providers(mcp_caps.get("providers", []))
    apps_str, windows_str = format_desktop_environment(
        computer_caps.get("available_apps", []),
        computer_caps.get("active_windows", []),
    )

    capability_section = CAPABILITY_TEMPLATE.format(
        mcp_providers=mcp_providers_str,
        platform=computer_caps.get("platform", "unknown"),
        available_apps=apps_str,
        active_windows=windows_str,
    )
    prompt_parts.append(capability_section)

    # Add execution context
    if state and state.results:
        previous_results_str = format_previous_results(state.results)
    else:
        previous_results_str = "None - this is the first step."

    context_section = CONTEXT_TEMPLATE.format(
        task=request.task,
        previous_results=previous_results_str,
    )
    prompt_parts.append(context_section)

    # Add failure reminder if last step failed
    if last_step_failed and failed_step_info:
        failure_section = FAILURE_REMINDER.format(
            failed_task=failed_step_info.get("task", "unknown"),
            failed_target=failed_step_info.get("target", "unknown"),
            failed_error=failed_step_info.get("error", "unknown"),
        )
        prompt_parts.append(failure_section)

    return "\n".join(prompt_parts)


def get_system_prompt() -> str:
    """
    Accessor for backward compatibility.

    Returns the static foundation prompt. For full dynamic prompts,
    use build_system_prompt() instead.
    """
    return STATIC_FOUNDATION


__all__ = [
    "STATIC_FOUNDATION",
    "build_system_prompt",
    "get_system_prompt",
    "format_mcp_providers",
    "format_desktop_environment",
    "format_previous_results",
]
