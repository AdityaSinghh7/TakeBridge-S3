from __future__ import annotations

"""
Task Compose Agent for the orchestrator.

Given a raw task string and current capabilities (MCP + desktop),
this module asks an LLM to produce a structured ComposedPlan and
performs lightweight validation/normalization.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from orchestrator_agent.composed_plan import ComposedPlan, ComposedStep
from shared.oai_client import respond_once, extract_assistant_text

logger = logging.getLogger(__name__)

COMPOSE_SCHEMA_VERSION = 1


def _summarize_capabilities(capabilities: Dict[str, Any]) -> Tuple[str, str]:
    """Build compact textual summaries of MCP providers and desktop apps."""
    mcp_caps = capabilities.get("mcp", {}) or {}
    computer_caps = capabilities.get("computer", {}) or {}

    providers = mcp_caps.get("providers", []) or []
    provider_lines: List[str] = []
    for p in providers:
        name = p.get("provider") or "unknown"
        tools = p.get("tools") or []
        preview = ", ".join(tools[:5])
        extra = ""
        if len(tools) > 5:
            extra = f", ... ({len(tools)} tools total)"
        provider_lines.append(f"- {name}: {preview}{extra}")
    mcp_summary = "\n".join(provider_lines) if provider_lines else "None"

    apps = computer_caps.get("available_apps", []) or []
    platform = computer_caps.get("platform", "unknown")
    apps_summary = (
        f"Platform: {platform}; Apps: " + (", ".join(apps) if apps else "None")
    )

    return mcp_summary, apps_summary


def _build_compose_prompt(task: str, capabilities: Dict[str, Any]) -> str:
    """Construct a system prompt describing the planning job and schema."""
    mcp_summary, apps_summary = _summarize_capabilities(capabilities)

    prompt = f"""
You are the Task Compose Agent for a higher-level orchestrator.

Your job:
- Take a raw user task and the current capabilities (MCP providers/tools and desktop apps).
- Decompose the task top-down into:
  - High-level subtasks (ComposedTask)
  - Detailed tool/app-level steps (ComposedStep)
- Prefer MCP tools when a suitable provider/tool exists.
- Use computer-use (CUA) steps when desktop UI automation is required.

You MUST respond with a single JSON object that matches this schema exactly:

{{
  "schema_version": 1,
  "original_task": "string",
  "notes": "optional string or null",
  "steps": [
    {{
      "id": "step-1",
      "type": "mcp" | "cua" | "meta",
      "description": "what this step does in natural language (for humans)",

      "provider_id": "gmail",        // for MCP steps, if known
      "tool_id": "gmail.get_last_emails",  // canonical provider.tool id, if known
      "tool_name": "gmail_get_last_emails", // optional display name

      "app_name": "LibreOffice Writer", // for CUA steps, if known
      "action_kind": "open_app" | "type_text" | "save_file" | "navigate" | "other",

      "prompt": "Short, explicit instruction that will be sent to the main agent loop for this step"
    }}
  ]
}}

CRITICAL REQUIREMENTS FOR THE "prompt" FIELD:

Each step's "prompt" field will be concatenated into a single task string that is sent to the main AI agent loop. Therefore:

1. **Self-contained**: Each prompt must be understandable on its own, without template variables or placeholders.

2. **No template syntax**: NEVER use template variables like {{step-1.emails}}, {{step-2.summary}}, or any other placeholder syntax. The main AI agent will not understand these.

3. **Reference previous steps naturally**: When a step depends on data from a previous step, describe what that previous step accomplished in natural language.

   ✅ GOOD examples:
   - "Summarize the content of the two emails that were retrieved in the previous step. Extract key information from both emails and prepare a concise summary."
   - "Type the email summary that was generated in the previous step into the new LibreOffice Writer document."
   - "Use the gmail_search tool to retrieve the last 2 emails from the user's inbox, returning full message bodies."

   ❌ BAD examples (DO NOT USE):
   - "Summarize: {{step-1.emails}}" 
   - "Type {{step-2.summary}} into the document"
   - "Use the data from {{previous_step}}"

4. **For MCP steps**: Be explicit about which tool to use and what parameters are needed.
   - Example: "Use the gmail_search tool to retrieve the last 2 emails from the user's inbox. Return full message bodies including subject, sender, and content."

5. **For CUA steps**: Clearly state the action and application.
   - Example: "Using CUA, open LibreOffice Writer application."
   - Example: "Using CUA, type the email summary that was generated in the previous step into the new document in LibreOffice Writer."

6. **For meta steps**: Describe what processing or transformation should happen.
   - Example: "Generate a concise summary of the two emails that were retrieved in the previous step. Extract the main points from each email and combine them into a single coherent summary."

7. **Flow naturally**: When concatenated, the prompts should read like a numbered list of instructions that the main AI agent can follow sequentially.

Capabilities summary (use only these providers/apps when possible):

MCP providers:
{mcp_summary}

Desktop apps:
{apps_summary}

Example of good prompt structure (do NOT include this example in your output, it is only guidance):

For a Gmail + LibreOffice task:
- Step 1 (MCP): "Use the gmail_search tool to retrieve the last 2 emails from the user's inbox. Return full message bodies including subject, sender, and content."
- Step 2 (meta): "Generate a concise summary of the two emails that were retrieved in the previous step. Extract the main points from each email and combine them into a single coherent summary."
- Step 3 (CUA): "Using CUA, open LibreOffice Writer application."
- Step 4 (CUA): "Using CUA, type the email summary that was generated in the previous step into the new document in LibreOffice Writer."
- Step 5 (CUA): "Using CUA, save the current document as 'email_summary.odt' in the Documents folder."

Important:
- Use realistic provider_id / tool_id / app_name values based on the capabilities summary when possible.
- It is OK if some fields are left null when you are not sure, but keep the structure valid.
- Each prompt must be self-contained and reference previous steps by describing what they accomplished.
- Keep the JSON concise but complete.

Now the user task you must decompose will be provided separately as 'original_task'.
"""
    # Keep newlines but strip leading/trailing whitespace for cleanliness
    return prompt.strip()


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON parsing from model output."""
    text = text.strip()
    if not text:
        return None
    # Some models may wrap JSON in markdown fences; strip them if present.
    if text.startswith("```"):
        # Remove first and last fenced code block markers
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1 if parts[0] == "" else 2]
            text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        logger.warning("Task compose agent returned non-JSON output; text=%r", text[:400])
        return None


def _clean_prompt_template_vars(prompt: Optional[str], step_id: str) -> Optional[str]:
    """
    Remove template variable syntax from prompts and replace with natural language references.
    
    This ensures prompts are self-contained and understandable by the main AI agent loop
    when concatenated into a single task string.
    """
    if not prompt:
        return prompt
    
    import re
    
    # Pattern to match template variables like {{step-1.emails}}, {{step-2.summary}}, etc.
    template_pattern = r'\{\{([^}]+)\}\}'
    
    def replace_template(match):
        var_expr = match.group(1).strip()
        # Try to extract meaningful context from the variable expression
        parts = var_expr.split('.')
        if len(parts) >= 2:
            step_ref = parts[0].strip()
            data_key = parts[1].strip()
            # Convert to natural language reference
            return f"the {data_key} from the previous step"
        elif 'step' in var_expr.lower():
            return "the result from the previous step"
        else:
            return "the data from the previous step"
    
    cleaned = re.sub(template_pattern, replace_template, prompt)
    
    # Log warning if we found and replaced template variables
    if cleaned != prompt:
        logger.warning(
            f"Cleaned template variables from prompt in step {step_id}. "
            f"Original had template syntax, replaced with natural language references."
        )
    
    return cleaned


def _build_minimal_plan(task: str) -> ComposedPlan:
    """Fallback plan when the LLM output is unusable."""
    step = ComposedStep(id="step-1", type="meta", description=task, prompt=task)
    return ComposedPlan(
        schema_version=COMPOSE_SCHEMA_VERSION,
        original_task=task,
        steps=[step],
        notes="Fallback minimal plan: LLM output was invalid or unavailable.",
        combined_prompt=task,
    )


def _normalize_plan_dict(
    raw: Dict[str, Any],
    capabilities: Dict[str, Any],
    *,
    original_task: str,
) -> ComposedPlan:
    """Convert a raw dict (from JSON) into a validated ComposedPlan."""
    schema_version = int(raw.get("schema_version") or COMPOSE_SCHEMA_VERSION)
    notes = raw.get("notes")

    # Prepare lookup sets for light validation
    mcp_caps = capabilities.get("mcp", {}) or {}
    providers = mcp_caps.get("providers", []) or []
    valid_providers = {p.get("provider") for p in providers if p.get("provider")}

    computer_caps = capabilities.get("computer", {}) or {}
    apps = computer_caps.get("available_apps", []) or []
    app_map = {a.lower(): a for a in apps if isinstance(a, str)}

    # Parse steps
    steps_in: List[Dict[str, Any]] = raw.get("steps") or []
    parsed_steps: List[ComposedStep] = []
    for s in steps_in:
        sid = str(s.get("id") or "").strip()
        stype = s.get("type") or "meta"
        desc = s.get("description") or original_task
        if not sid:
            # Skip steps without IDs
            continue

        # Extract and clean the prompt field
        raw_prompt = s.get("prompt")
        cleaned_prompt = _clean_prompt_template_vars(raw_prompt, sid) if raw_prompt else None

        step = ComposedStep(
            id=sid,
            type=stype,  # type: ignore[arg-type]
            description=str(desc),
            provider_id=s.get("provider_id"),
            tool_id=s.get("tool_id"),
            tool_name=s.get("tool_name"),
            app_name=s.get("app_name"),
            action_kind=s.get("action_kind"),
            prompt=cleaned_prompt,
        )

        # Light normalization
        if step.type == "mcp":
            if step.provider_id and step.provider_id not in valid_providers:
                # Unknown provider – downgrade to meta but keep description
                step.type = "meta"  # type: ignore[assignment]
        if step.type == "cua":
            if step.app_name:
                key = step.app_name.lower()
                if key in app_map:
                    step.app_name = app_map[key]

        parsed_steps.append(step)

    # Build combined prompt by concatenating step prompts/descriptions
    pieces: List[str] = []
    for idx, step in enumerate(parsed_steps, start=1):
        text = step.prompt or step.description
        pieces.append(f"{idx}. {text}")
    combined_prompt = "\n".join(pieces) if pieces else original_task

    return ComposedPlan(
        schema_version=schema_version,
        original_task=original_task,
        steps=parsed_steps,
        notes=notes,
        combined_prompt=combined_prompt,
    )


def compose_plan(
    task: str,
    capabilities: Dict[str, Any],
    *,
    tool_constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """High-level entry point to build a composed plan for a task.

    Returns:
        Dict[str, Any]: JSON-serializable composed plan.
    """
    system_prompt = _build_compose_prompt(task, capabilities)

    # User message: keep it simple, original_task is echoed so the model
    # doesn't have to infer field names.
    user_content = json.dumps(
        {
            "original_task": task,
            "tool_constraints": tool_constraints or None,
        },
        ensure_ascii=False,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # First attempt
    raw_text = ""
    try:
        resp = respond_once(messages=messages)
        raw_text = extract_assistant_text(resp)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Task compose agent call failed on first attempt: %s", exc)
        plan = _build_minimal_plan(task)
        return plan.to_dict()

    plan_dict = _safe_parse_json(raw_text)

    # Retry once with explicit JSON reminder if needed
    if plan_dict is None:
        retry_messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "You previously responded with invalid JSON. "
                    "Respond again with ONLY valid JSON matching the schema, no explanations.\n"
                    + user_content
                ),
            },
        ]
        try:
            resp = respond_once(messages=retry_messages)
            raw_text = extract_assistant_text(resp)
            plan_dict = _safe_parse_json(raw_text)
        except Exception as exc:  # pragma: no cover
            logger.exception("Task compose agent call failed on retry: %s", exc)
            plan_dict = None

    if plan_dict is None:
        plan = _build_minimal_plan(task)
        return plan.to_dict()

    try:
        normalized = _normalize_plan_dict(plan_dict, capabilities, original_task=task)
        return normalized.to_dict()
    except Exception as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to normalize composed plan, falling back. Error: %s", exc)
        plan = _build_minimal_plan(task)
        return plan.to_dict()


__all__ = ["compose_plan", "COMPOSE_SCHEMA_VERSION"]


