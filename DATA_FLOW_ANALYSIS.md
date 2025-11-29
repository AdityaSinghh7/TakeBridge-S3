# Orchestrator Data Flow Analysis & Fixes

## Issue: Data Loss Between MCP → Orchestrator → Computer-Use

When the orchestrator uses MCP agent to retrieve data in Step 1, then needs to pass that data to computer-use agent in Step 2, data could be lost at multiple points.

## Root Causes Identified & Fixed

### 1. ✅ FIXED: System Prompt Not Exposing Retrieved Data

**Problem:** [orchestrator_agent/system_prompt.py:272-294](orchestrator_agent/system_prompt.py:272-294)

The `format_previous_results()` function only showed summaries, not actual retrieved data:

```python
# BEFORE (❌ Data hidden)
summary = r.output.get("summary", "No summary")
lines.append(f"{i}. {status_icon} {r.target.upper()}: {r.next_task}\n   Result: {summary}")
```

**Fix Applied:**
```python
# AFTER (✅ Data exposed)
translated = output.get("translated", {})
artifacts = translated.get("artifacts", {})
retrieved_data = artifacts.get("retrieved_data", {})

if retrieved_data:
    step_text += "\n   Retrieved Data:"
    for key, value in retrieved_data.items():
        step_text += f"\n     - {key}: {value_str}"
```

**Impact:** Orchestrator LLM can now see actual retrieved data (filenames, paths, IDs, etc.) when planning the next step.

---

### 2. ✅ FIXED: Translator Truncating Raw Data

**Problem:** [orchestrator_agent/translator.py:210](orchestrator_agent/translator.py:210)

```python
# BEFORE (❌ Only 2000 chars)
raw_preview = json.dumps(raw_result, ensure_ascii=False)[:2000]
```

**Fix Applied:**
```python
# AFTER (✅ 8000 chars)
raw_preview = json.dumps(raw_result, ensure_ascii=False)[:8000]
```

**Impact:** Translator LLM can now see 4x more data before truncation, preserving larger datasets from MCP agent.

---

### 3. ✅ FIXED: Fallback Not Preserving MCP Data

**Problem:** [orchestrator_agent/translator.py:245-257](orchestrator_agent/translator.py:245-257)

Deterministic fallback looked for `artifacts` field, but MCP returns `raw_outputs`:

```python
# BEFORE (❌ Generic fallback)
"artifacts": raw_result.get("artifacts") or [],
```

**Fix Applied:**
```python
# AFTER (✅ Agent-specific extraction)
if target == "mcp":
    raw_outputs = raw_result.get("raw_outputs", {})
    artifacts["tool_outputs"] = [{"tool": k, "result": v} for k, v in raw_outputs.items()]

    # Extract from steps (sandbox outputs)
    for step_item in steps:
        outcome = step_item.get("action_outcome", {})
        if isinstance(outcome, dict):
            retrieved_data.update(outcome)
```

**Impact:** Even if LLM translation fails, data is preserved via deterministic extraction.

---

## Complete Data Flow (After Fixes)

```
Step 1: MCP Agent Retrieves Data
  ├─ execute_mcp_task("Get Gmail attachment")
  ├─ Returns MCPTaskResult:
  │    ├─ raw_outputs: {"tool.gmail.get_attachment": {...}}
  │    ├─ steps: [{action_outcome: {"filename": "invoice.pdf", "path": "~/Downloads/..."}}]
  │    └─ final_summary: "Retrieved attachment"
  ↓
Translator (translator.py)
  ├─ LLM sees 8000 chars of raw_result (was 2000) ✅
  ├─ Extracts to canonical format:
  │    └─ artifacts.retrieved_data: {"filename": "invoice.pdf", "path": "~/Downloads/invoice.pdf"}
  ├─ OR fallback extracts from raw_outputs directly ✅
  ↓
StepResult stored with full artifacts
  ↓
Step 2: Orchestrator Planning
  ├─ system_prompt includes previous results ✅
  ├─ Shows retrieved_data with actual values ✅
  ├─ Orchestrator LLM sees:
  │    "1. ✅ MCP: Get Gmail attachment
  │     Result: Retrieved attachment
  │     Retrieved Data:
  │       - filename: invoice.pdf
  │       - path: ~/Downloads/invoice.pdf"
  ├─ LLM crafts specific task:
  │    "Open the file ~/Downloads/invoice.pdf in Preview app"
  ↓
Step 3: Computer-Use Agent
  ├─ Receives task with concrete file path ✅
  └─ Executes desktop automation
```

---

## Data Preservation Guidelines for MCP Agent

To ensure data flows correctly to computer-use agent:

### ✅ For Single Tool Calls

**MCP Agent returns data in `raw_outputs`:**
```python
{
  "raw_outputs": {
    "tool.gmail.gmail_get_attachment": {
      "filename": "invoice_march_2024.pdf",
      "download_url": "https://...",
      "size_bytes": 245678
    }
  }
}
```

**Translator extracts to:**
```python
{
  "artifacts": {
    "tool_outputs": [...],
    "retrieved_data": {
      "filename": "invoice_march_2024.pdf",
      "download_url": "https://...",
      "size_bytes": 245678
    }
  }
}
```

### ✅ For Sandbox Calls

**MCP Agent returns data in step outcomes:**
```python
{
  "steps": [
    {
      "action_type": "sandbox",
      "action_outcome": {
        "processed_data": {...},
        "output_file": "/tmp/result.csv"
      }
    }
  ]
}
```

**Translator extracts to:**
```python
{
  "artifacts": {
    "retrieved_data": {
      "processed_data": {...},
      "output_file": "/tmp/result.csv"
    },
    "code_executed": ["import pandas as pd..."]
  }
}
```

---

## Testing the Data Flow

Use the orchestrator test script to verify:

```bash
python scripts/run_dev_orchestrator.py \
  --task "Use Gmail to find my most recent email with an attachment, download it, and open it in Preview" \
  --verbose
```

Expected output showing data preservation:
```
📋 STEP 1 - PLANNING DECISION
  Agent Selected: MCP
  Task: Use Gmail provider's gmail_search tool to find emails with attachments...

✅ STEP 1 - COMPLETED
  MCP AGENT EXECUTION
    Summary: Retrieved email from john@example.com with attachment invoice.pdf
    Tool Calls: 2 tool call(s)
    Retrieved Data:            # ← Data is preserved!
      - attachment_filename: invoice_march_2024.pdf
      - attachment_path: ~/Downloads/invoice_march_2024.pdf
      - email_subject: March Invoice

📋 STEP 2 - PLANNING DECISION
  Agent Selected: COMPUTER_USE
  Task: Open the file ~/Downloads/invoice_march_2024.pdf in Preview app
        # ↑ Orchestrator sees the path and uses it!

✅ STEP 2 - COMPLETED
  COMPUTER-USE AGENT EXECUTION
    Summary: Opened invoice_march_2024.pdf in Preview application
```

---

## Summary

✅ **System prompt** now exposes `artifacts.retrieved_data` to orchestrator LLM
✅ **Translator** preserves 4x more data (8000 chars vs 2000)
✅ **Fallback** extracts data from MCP `raw_outputs` and `steps[]`
✅ **Data flows** correctly from MCP → orchestrator → computer-use

The orchestrator can now correctly handle hybrid workflows where data retrieved by the MCP agent needs to be used by the computer-use agent in subsequent steps.
