from __future__ import annotations

"""
LLM-backed translator that converts self-contained markdown trajectories into the
canonical output format.

CRITICAL CHANGE: Translator now receives ONLY trajectory_md (self-contained markdown),
not raw_result. The trajectory contains all necessary data.

If the LLM call fails or is unavailable, we fall back to a deterministic parser.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from orchestrator_agent.data_types import AgentTarget

try:  # Optional dependency
    from shared.oai_client import OAIClient, extract_assistant_text
except Exception:  # pragma: no cover
    OAIClient = None  # type: ignore
    extract_assistant_text = None  # type: ignore

logger = logging.getLogger(__name__)


TRANSLATOR_SYSTEM_PROMPT = """\
You are a translator that converts self-contained markdown trajectories from worker agents into a canonical JSON format for the orchestrator.

## Your Role

You receive execution trajectories from either:
1. **MCP Agent** - API-based tool execution (search, tool calls, sandbox code)
2. **Computer-Use Agent** - Desktop UI automation (clicks, observations, reflections)

The trajectory is a COMPLETE self-contained markdown document with ALL data needed. There are no separate raw outputs - everything is in the markdown.

You act as a *cleaning and formatting agent* for the orchestrator: your job is to restructure what the worker provided into the canonical JSON without inventing or omitting task-relevant information. Preserve key facts, but do not copy long text verbatim when a concise, task-relevant summary will do.

Your task is to extract and organize this into a decisive canonical JSON format that enables the orchestrator to:
- Determine overall success/failure
- Identify exact failure points
- Understand what each step accomplished
- Make informed decisions about next steps

## Critical Rules

### Data Extraction
- **EXTRACT ALL key data** from the markdown (tool responses, UI observations, errors)
- **KEEP key fields exact** (IDs, timestamps, subjects, senders, counts, statuses). For large free-form text, summarize into task-relevant facts instead of copying the entire text.
- **COUNT accurately** - total steps, tools found, etc.
- **IDENTIFY failures precisely** - which step number failed, what the error was
- When deciding what to keep, ask: "What does the task need?" Keep information that serves the task; avoid copying unrelated bulk text.

### No Invention
- **NEVER fabricate** data, counts, or values not in the trajectory
- **NEVER guess** at missing information - use null
- **QUOTE DIRECTLY** from trajectory for errors and summaries

## Markdown Trajectory Formats

### MCP Agent Format

```markdown
### Step N: Search - provider_name
**Query**: search query text
**Found**: N tool(s)
**Tools**:
- `tool.id`: Tool description

### Step N: Tool Call - tool.name
**Arguments**:
```json
{args}
```
**Response**:
```json
{response}
```
*(Response summarized via LLM)*  <!-- Optional -->

### Step N: Sandbox Execution
**Code**:
```python
code here
```
**Output**:
```json
{output}
```

### Step N: Completion|Failure
**Reasoning**: reason text
**Summary**: summary text
**Error**: error message  <!-- If failed -->
```

### Computer-Use Agent Format

```markdown
## Step N

### Worker Agent
**Plan**: what the agent plans to do
**Action**: `pyautogui.click(x, y)`
**Execution Result**:
```json
{result}
```

### Reflection Agent
**Reflection**: reflection text
**Thoughts**: reasoning

### Behaviour Narrator
**Observation**: what changed in UI
**Analysis**: detailed analysis

### Code Agent
**Summary**: code execution summary
**Completion**: DONE|FAIL|BUDGET_EXHAUSTED
**Execution History**:
  Step N:
    **Code**: ```code```
    **Thoughts**: reasoning

## Final Status
**Status**: success|failed|timeout
**Completion Reason**: DONE|FAIL|MAX_STEPS_REACHED
```

## Canonical Output Structure

You MUST output this EXACT JSON structure with ALL fields:

```json
{
  "task": "string - the task description",
  "overall_success": boolean,
  "summary": "string - 2-3 sentences describing full execution",
  "error": "string | null",
  "error_code": "string | null",
  "last_step_failed": boolean,
  "failed_step_index": integer | null,
  "total_steps": integer,
  "steps_summary": [
    "string - Step N: action taken. Outcome observed."
  ],
  "data": {
    "NOTE": "OPTIONAL - Only include this field for data fetch/read operations",
    "emails": "array - For email fetching, include key email data (sender, subject, snippet)",
    "records": "array - For database queries, include relevant record data",
    "content": "string - For file reads, include relevant content summary",
    "NOTE2": "Summarize to task-relevant parts only, not full dumps"
  },
  "artifacts": {
    "tool_calls": [
      {
        "tool_id": "string",
        "arguments": object,
        "response": object,
        "success": boolean
      }
    ],
    "ui_observations": ["string"],
    "code_executions": [
      {
        "code": "string",
        "output": any,
        "success": boolean
      }
    ],
    "search_results": [
      {
        "query": "string",
        "tools_found": integer,
        "tool_names": ["string"]
      }
    ]
  }
}
```

## Field Definitions

- **task**: Extract from context or use provided task string
- **overall_success**: `true` if task completed successfully, `false` if failed
- **summary**: 2-3 sentence natural language summary of entire execution
- **error**: Error message from failure step, `null` if overall_success=true
- **error_code**: Machine-readable code (e.g., "tool_execution_failed"), `null` if success
- **last_step_failed**: `true` ONLY if the very last/final step shows failure
- **failed_step_index**: 1-based index of first step that failed, `null` if overall_success=true
- **total_steps**: Count of steps executed (from markdown headers)
- **steps_summary**: Array with one entry per step - natural language "Step N: [action]. [outcome]"
  - **artifacts.tool_calls**: Every MCP tool call with args, response, success extracted from markdown
  - **artifacts.ui_observations**: Every behaviour narrator observation from computer-use
  - **artifacts.code_executions**: Sandbox and code agent executions with code and output
  - **artifacts.search_results**: Every search with query, count, and tool names found

## Examples

### MCP Success Example

Input:
```
### Step 1: Search - gmail
**Query**: emails from john
**Found**: 2 tool(s)
**Tools**:
- `gmail.gmail_search`: Search emails

### Step 2: Tool Call - gmail.gmail_search
**Arguments**:
{"query": "from:john@example.com"}
**Response**:
{"messages": [{"id": "1", "subject": "Hello"}], "count": 1}

### Step 3: Completion
**Reasoning**: Found email successfully
**Summary**: Retrieved 1 email from john@example.com
```

Output:
```json
{
  "task": "Find emails from john",
  "overall_success": true,
  "summary": "Searched Gmail for emails from john@example.com and found 1 email. Successfully retrieved the email with subject 'Hello'.",
  "error": null,
  "error_code": null,
  "last_step_failed": false,
  "failed_step_index": null,
  "total_steps": 3,
  "steps_summary": [
    "Step 1: Searched gmail for 'emails from john', found 2 tools including gmail.gmail_search",
    "Step 2: Called gmail.gmail_search with query='from:john@example.com'. Response: 1 message found",
    "Step 3: Completion - Retrieved 1 email from john@example.com"
  ],
  "data": {
    "emails": [
      {
        "sender": "john@example.com",
        "subject": "Hello",
        "messageId": "1"
      }
    ]
  },
  "artifacts": {
    "tool_calls": [
      {
        "tool_id": "gmail.gmail_search",
        "arguments": {"query": "from:john@example.com"},
        "response": {"messages": [{"id": "1", "subject": "Hello"}], "count": 1},
        "success": true
      }
    ],
    "ui_observations": [],
    "code_executions": [],
    "search_results": [
      {
        "query": "emails from john",
        "tools_found": 2,
        "tool_names": ["gmail.gmail_search"]
      }
    ]
  }
}
```

### Computer-Use Failure Example

Input:
```
## Step 1

### Worker Agent
**Plan**: Click Submit button
**Action**: `pyautogui.click(500, 300)`
**Execution Result**:
{"success": true}

### Behaviour Narrator
**Observation**: Button clicked, but form validation error appeared

## Step 2

### Worker Agent
**Plan**: Try to click OK on error
**Action**: `pyautogui.click(600, 400)`
**Execution Result**:
{"success": false, "error": "Element not found"}

## Final Status
**Status**: failed
**Completion Reason**: FAIL
```

Output:
```json
{
  "task": "Submit form",
  "overall_success": false,
  "summary": "Attempted to click Submit button which showed a validation error. Tried to dismiss error dialog but encountered 'Element not found' error. Task failed at step 2.",
  "error": "Element not found",
  "error_code": "execution_failed",
  "last_step_failed": true,
  "failed_step_index": 2,
  "total_steps": 2,
  "steps_summary": [
    "Step 1: Clicked Submit button at (500, 300). Observation: Button clicked, but form validation error appeared",
    "Step 2: Attempted to click OK on error dialog. Execution failed: Element not found"
  ],
  "artifacts": {
    "tool_calls": [],
    "ui_observations": [
      "Button clicked, but form validation error appeared"
    ],
    "code_executions": [],
    "search_results": []
  }
}
```

## Important Notes

- Always include ALL required fields in output
- steps_summary must have exactly `total_steps` entries
- last_step_failed=true means agent is stuck and needs different approach
- Extract actual data from JSON blocks in markdown - don't summarize
- Count step headers accurately (## Step N or ### Step N)
- If trajectory shows error in last step, last_step_failed=true
- If the computer-use agent's trajectory has a save_to_knowledge call, include the exact data that was saved to the knowledge bank in the data field.
"""


def _build_messages(task: str, target: AgentTarget, trajectory: str) -> list[dict]:
    """Build LLM messages for translation."""
    user_content = (
        f"Task: {task}\n"
        f"Agent type: {target}\n"
        "Trajectory (markdown follows):\n"
        "```markdown\n"
        f"{trajectory}\n"
        "```\n"
        "Instruction: Translate the trajectory markdown into the canonical JSON format. "
        "Extract all data from the markdown - there are no other inputs. "
        "Return ONLY valid JSON with all required fields."
    )
    return [
        {"role": "system", "content": TRANSLATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _safe_json_load(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from text, handling markdown code fences."""
    try:
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            # Remove opening fence (```json or ```)
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        return json.loads(text)
    except Exception:
        return None


def _deterministic_fallback(task: str, target: AgentTarget, trajectory: str) -> Dict[str, Any]:
    """Deterministic parser for trajectory markdown when LLM is unavailable."""
    # Count steps
    step_pattern = r"^#{1,3}\s+Step\s+(\d+)" if target == "mcp" else r"^##\s+Step\s+(\d+)"
    step_matches = re.findall(step_pattern, trajectory, re.MULTILINE)
    total_steps = len(step_matches)

    # Check for errors
    error_match = re.search(r"\*\*Error\*\*:\s*(.+?)(?:\n|$)", trajectory)
    error = error_match.group(1).strip() if error_match else None

    # Check final status
    status_match = re.search(r"\*\*Status\*\*:\s*(\w+)", trajectory)
    completion_match = re.search(r"\*\*Completion Reason\*\*:\s*(\w+)", trajectory)

    status = status_match.group(1) if status_match else "unknown"
    completion = completion_match.group(1) if completion_match else "unknown"

    overall_success = (status in ("success", "completed") or completion == "DONE") and not error
    last_step_failed = error is not None or status == "failed" or completion == "FAIL"

    # Extract steps summary
    steps_summary = []
    lines = trajectory.split("\n")
    current_step_text = []
    current_step_num = None

    for line in lines:
        step_header_match = re.match(step_pattern, line)
        if step_header_match:
            # Save previous step
            if current_step_num and current_step_text:
                summary = " ".join(current_step_text[:3])  # First 3 lines
                steps_summary.append(f"Step {current_step_num}: {summary}")
            current_step_num = step_header_match.group(1)
            current_step_text = []
        elif current_step_num and line.strip():
            # Collect step text (skip markdown formatting)
            clean_line = re.sub(r'\*\*|\`\`\`|\#\#\#', '', line).strip()
            if clean_line and not clean_line.startswith("```"):
                current_step_text.append(clean_line)

    # Save last step
    if current_step_num and current_step_text:
        summary = " ".join(current_step_text[:3])
        steps_summary.append(f"Step {current_step_num}: {summary}")

    return {
        "task": task,
        "overall_success": overall_success,
        "summary": f"Executed {total_steps} step(s). " + ("Task completed." if overall_success else f"Failed: {error or 'Unknown error'}"),
        "error": error,
        "error_code": "execution_failed" if error else None,
        "last_step_failed": last_step_failed,
        "failed_step_index": int(step_matches[-1]) if not overall_success and step_matches else None,
        "total_steps": total_steps,
        "steps_summary": steps_summary or [f"Step execution summary unavailable"],
        "artifacts": {
            "tool_calls": [],
            "ui_observations": [],
            "code_executions": [],
            "search_results": [],
        },
    }


def translate_step_output(
    *,
    task: str,
    target: AgentTarget,
    trajectory: str,
    debug_step_id: Optional[str] = None,
    llm_client: Optional[Any] = None,
    llm_model: str = "o4-mini",
    max_output_tokens: int = 16000,
) -> Dict[str, Any]:
    """
    Translate self-contained markdown trajectory into canonical format.

    IMPORTANT: Only trajectory is provided. NO raw_result or raw_outputs.
    The trajectory contains all necessary data.

    Args:
        task: The task description
        target: Agent type (mcp or computer_use)
        trajectory: Self-contained markdown trajectory with ALL data
        debug_step_id: Optional step identifier used only for logging/debugging
        llm_client: Optional LLM client
        llm_model: Model to use for translation
        max_output_tokens: Max tokens for LLM response

    Returns:
        Canonical dictionary with decisive format
    """
    logger.info(
        "translator.enter target=%s step_id=%s trajectory_len=%s",
        target,
        debug_step_id,
        len(trajectory),
    )

    client = llm_client
    if client is None and OAIClient is not None:
        try:
            client = OAIClient()
            logger.info("translator.llm_client_ready target=%s", target)
        except Exception:
            logger.info("translator.llm_client_unavailable target=%s", target)
            client = None

    if client:
        try:
            messages = _build_messages(task, target, trajectory)
            try:
                response = client.create_response(
                    messages=messages,
                    model=llm_model,
                    max_output_tokens=max_output_tokens,
                    reasoning_effort="medium",
                    text={"format": {"type": "json_object"}},
                )
            except TypeError:
                # Older SDKs may not support json mode yet; fall back to plain text.
                response = client.create_response(
                    messages=messages,
                    model=llm_model,
                    max_output_tokens=max_output_tokens,
                    reasoning_effort="medium",
                )
            text = None
            if extract_assistant_text is not None:
                try:
                    text = extract_assistant_text(response)
                except Exception:
                    text = None
            if not text:
                text = getattr(response, "output_text", None) or getattr(
                    response, "text", None
                )
            if isinstance(text, str):
                parsed = _safe_json_load(text)
                if parsed and isinstance(parsed, dict):
                    # Validate required fields
                    required = ["task", "overall_success", "summary", "total_steps", "steps_summary", "artifacts"]
                    missing = [k for k in required if k not in parsed]
                    if not missing:
                        logger.info("translator.llm_success target=%s", target)
                        return parsed
                    logger.info("translator.llm_missing_fields target=%s missing=%s", target, missing)
                else:
                    logger.info("translator.llm_invalid_json target=%s parsed_type=%s", target, type(parsed))
            else:
                logger.info("translator.llm_no_text target=%s text_type=%s", target, type(text))
            logger.info("translator.llm_parse_failed target=%s", target)
        except Exception as exc:  # pragma: no cover
            logger.info("translator.llm_error target=%s error=%s", target, exc)

    # Deterministic fallback
    logger.info("translator.fallback target=%s", target)
    return _deterministic_fallback(task, target, trajectory)


__all__ = ["translate_step_output", "TRANSLATOR_SYSTEM_PROMPT"]
