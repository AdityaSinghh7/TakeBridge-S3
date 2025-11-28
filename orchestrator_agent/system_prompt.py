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
    Format previous step results for context.

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
        status_icon = "✅" if r.success else "❌"

        # Get the translated output if available
        output = r.output or {}
        translated = output.get("translated", {})

        # Get summary
        summary = translated.get("summary", output.get("summary", "No summary"))

        # Build step result
        step_text = (
            f"{i}. {status_icon} {r.target.upper()}: {r.next_task}\n"
            f"   Result: {summary}"
        )

        # CRITICAL: Include retrieved data from artifacts
        artifacts = translated.get("artifacts", {})
        retrieved_data = artifacts.get("retrieved_data", {})

        # Special handling for MCP search/discovery results
        # For search actions, only show tool names (not full specs)
        is_search_result = False
        if r.target == "mcp" and retrieved_data:
            # Check if this was a search action by looking for "found_tools"
            search_tools = retrieved_data.get("found_tools")
            tool_count = retrieved_data.get("count")

            if search_tools and isinstance(search_tools, list):
                is_search_result = True
                # Extract just the tool IDs/names
                tool_names = []
                for tool in search_tools[:10]:  # Limit to first 10
                    if isinstance(tool, dict):
                        tool_id = tool.get("tool_id", "")
                        if tool_id:
                            tool_names.append(tool_id)

                if tool_names:
                    step_text += f"\n   Tools Found: {tool_count or len(tool_names)} tool(s)"
                    step_text += f"\n     {', '.join(tool_names)}"

        # Include tool call count for actual tool invocations (not searches)
        tool_outputs = artifacts.get("tool_outputs", [])
        if tool_outputs and r.target == "mcp" and not is_search_result:
            step_text += f"\n   Tools Called: {len(tool_outputs)} tool call(s)"

        # Surface UI observations for computer-use steps
        ui_observations = artifacts.get("ui_observations", [])
        if ui_observations:
            step_text += "\n   UI Observations:"
            for obs in ui_observations[:3]:
                obs_str = _render_json(obs, max_chars=1000)
                step_text += f"\n     - {obs_str}"
            if len(ui_observations) > 3:
                step_text += f"\n     ... ({len(ui_observations) - 3} more)"

        # Include file information
        files_created = artifacts.get("files_created", [])
        if files_created:
            step_text += f"\n   Files Created: {', '.join(files_created[:5])}"

        # Provide a full translated JSON block for downstream planners
        if translated:
            # Show the full translated payload as the primary data block.
            full_json = _render_json(translated, max_chars=None)
            indented = "\n".join(f"     {line}" for line in full_json.splitlines())
            step_text += f"\n   Translated data:\n{indented}"

        lines.append(step_text)

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
