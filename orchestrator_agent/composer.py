from __future__ import annotations

"""
Task Compose Agent for the orchestrator.

Given a raw task string and current capabilities (MCP + desktop),
this module asks an LLM to produce a structured ComposedPlan and
performs lightweight validation/normalization.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from orchestrator_agent.composed_plan import ComposedPlan, ComposedStep
from shared.llm_client import respond_once, extract_assistant_text

logger = logging.getLogger(__name__)

COMPOSE_SCHEMA_VERSION = 2


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
    actions = computer_caps.get("actions", []) or []
    platform = computer_caps.get("platform", "unknown")
    apps_label = ", ".join(apps) if apps else "None"
    actions_label = ", ".join(actions) if actions else "None"
    apps_summary = f"Platform: {platform}; Apps: {apps_label}; Actions: {actions_label}"

    return mcp_summary, apps_summary


def _build_compose_prompt(task: str, capabilities: Dict[str, Any]) -> str:
    """Construct a system prompt describing the planning job and schema."""
    mcp_summary, apps_summary = _summarize_capabilities(capabilities)

    prompt = f"""
You are the Task Decomposition Agent. 

Your goal is to decompose a user request into a high-level sequential plan. 
You have two sub-agents you can delegate work to:
1. **MCP Agent**: Uses API tools (providers) to fetch data, search, or interact with services.
2. **Computer Use Agent (CUA)**: Uses a desktop GUI to interact with applications (open apps, navigate websites, type documents).

### **Planning Rules**
1. **Granularity**: Create **medium-level tasks**. Do not generate atomic actions (like "click button" or "type key"). 
   - Both agents are capable of handling multi-turn instructions.
   - Example (Good): "Research the history of Rome and summarize it."
   - Example (Bad): "Open browser", "Type 'Rome'", "Press Enter".

2. **Delegation**:
   - Assign tasks to **MCP** when a suitable tool/provider exists (faster, more reliable).
   - Assign tasks to **CUA** when UI interaction is required or no API tool exists.

3. **Step Boundaries**: Create a new step only when:
   - **Data Transfer**: Information fetched by one agent is needed by the next.
   - **Context Switch**: Switching from API work to Desktop work (or vice versa).
   - **Logical Isolation**: A distinct phase of the project is complete.

4. **Task Definition**:
   - For **MCP**: You MUST mention the `provider_id` and `tool_names` capable of doing the work.
   - For **CUA**: You MUST mention the `app_name` required.

### **Defining Outcomes (`expected_outcome`)**
You must clearly define what the orchestrator should expect at the end of each step:
- **For Retrieval Steps** (e.g., Search, Read): Define exactly what **data** needs to be returned for future steps (e.g., "The body text of the last 3 emails").
- **For Mutation/Action Steps** (e.g., Send, Save, Type): Define the **success criteria** or state change (e.g., "Confirmation that the file 'report.txt' is saved on Desktop").

### **Output Schema**
Respond with a single JSON object matching this schema:

{{
  "original_task": "string",
  "steps": [
    {{
      "id": "step-1",
      "type": "mcp" | "cua",
      "description": "High-level description of what this step achieves",
      
      // Routing Metadata
      "provider_id": "google_workspace",   // Required for MCP
      "tool_id": "gmail_search",           // Primary tool hint (optional)
      "app_name": "Chrome",                // Required for CUA
      
      // The Instruction
      "prompt": "The actual natural language instruction sent to the sub-agent. Be descriptive.",
      
      // The Outcome
      "expected_outcome": "Description of the data returned OR the action completed."
    }}
  ]
}}

### **Capabilities**
**MCP Providers (APIs):**
{mcp_summary}

**Computer Use Agent (GUI + action primitives):**
{apps_summary}

### **Prompting Best Practices**
- The `prompt` field should be self-contained. 
- If a step needs data from a previous step, reference it naturally (e.g., "Using the email summary retrieved in the previous step..."). 
- DO NOT use template variables like `{{step1.result}}`. Use English.

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
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    # If the content starts with a "json" language tag on its own line, drop it.
    if text.lower().startswith("json"):
        first_line, _, remainder = text.partition("\n")
        if first_line.strip().lower() == "json" and remainder.lstrip().startswith(("{", "[")):
            text = remainder.lstrip()
    try:
        return json.loads(text)
    except Exception as exc:
        logger.warning(
            "Task compose agent returned non-JSON output; error=%s text=%r",
            exc,
            text[:400],
        )
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
        outcome = s.get("expected_outcome")

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
            expected_outcome=outcome,
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
        logger.info("Calling LLM for compose_plan - task: %s", task[:100])
        resp = respond_once(messages=messages)
        raw_text = extract_assistant_text(resp)
        logger.info("LLM response received - length: %d chars, preview: %s", len(raw_text), raw_text[:200])
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Task compose agent call failed on first attempt: %s", exc)
        plan = _build_minimal_plan(task)
        return plan.to_dict()

    plan_dict = _safe_parse_json(raw_text)

    # Retry once with explicit JSON reminder if needed
    if plan_dict is None:
        logger.info("LLM response was not valid JSON, retrying with JSON reminder")
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
            logger.info("LLM retry response received - length: %d chars, preview: %s", len(raw_text), raw_text[:200])
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
