# Frontend SSE Event Guide

EventSource responses from `POST /orchestrate/stream` use `event: <name>` plus `data: <json>`.
Parse `data` with `JSON.parse(event.data)` and branch on `event.type` (or `event` in Fetch stream readers).
Only the events below are required/most useful to drive frontend updates; other telemetry can be ignored.

## Orchestrator Agent
- `orchestrator.planning.completed`
  - Purpose: planner finished choosing what to do next (or to stop).
  - Payload: `decision_type` (`next_step` | `task_complete` | `task_impossible`), `target` (`mcp` | `computer_use` | null), `task_preview` (string preview of the next task).
- `orchestrator.step.completed`
  - Purpose: one orchestrator step finished executing.
  - Payload: `step_id` (string), `status` (`completed` | `failed`), `success` (boolean).

## Computer-Use Agent
- `runner.started`
  - Purpose: computer-use runner kicked off.
  - Payload: `task` (string), `max_steps` (int), `platform` (string or null).
- `runner.step.agent_response`
  - Purpose: worker LLM responded with the next GUI action.
  - Payload: `step` (int), `action` (raw action text), `exec_code` (pyautogui snippet to execute), `normalized_action` (uppercased action token), `info` (object with `plan`, `reflection`, `reflection_thoughts`, optional `code_agent_output`).
- `runner.step.completed`
  - Purpose: a single computer-use step finished.
  - Payload: `step` (int), `status` (`success` | `failed` | `in_progress`), `action` (string), `completion_reason` (`DONE` | `FAIL` | null when still running).
- `runner.step.behavior`
  - Purpose: behavior narrator summary of visual changes for the step.
  - Payload: `step` (int), `fact_answer` (caption string), `fact_thoughts` (reasoning string).
- `runner.completed`
  - Purpose: computer-use runner finished.
  - Payload: `status` (`success` | `failed` | `timeout`), `completion_reason` (`DONE` | `FAIL` | `MAX_STEPS_REACHED` | `timeout`), `steps` (int count).
- `worker.reflection.completed`
  - Purpose: reflection agent produced thoughts on the trajectory so far.
  - Payload: `step` (int), `reflection` (text), `thoughts` (string with `<thoughts>` content).
- `worker.step.ready`
  - Purpose: consolidated per-step inputs before execution (plan + grounding).
  - Payload: `step` (int), `plan` (LLM plan text), `plan_code` (pyautogui code block from plan), `exec_code` (evaluated code to run), `reflection`, `reflection_thoughts`, `previous_behavior_thoughts`, `previous_behavior_answer`.
  - Frontend tip: use this for showing planned action/exec_code; pair with `runner.step.behavior` for state change captions and `worker.reflection.completed` for reflective notes rather than duplicating.
- `code_agent.session.started`
  - Purpose: code agent engaged (full-task or subtask).
  - Payload: `task` (string instruction), `budget` (max steps).
- `code_agent.step.response`
  - Purpose: code agent produced the next action/thoughts.
  - Payload: `step` (int), `action` (may include ```python/```bash blocks), `thoughts` (reasoning text).
- `code_agent.step.execution`
  - Purpose: execution result of the proposed code.
  - Payload: `step` (int), `code_type` (`python` | `bash` | null), `status` (`ok` | `error` | `skipped`), `output` (stdout), `error` (stderr/message), `message` (additional text), `return_code` (int or null).
- `code_agent.step.completed`
  - Purpose: code agent finished one step.
  - Payload: `step` (int), `status` (string status), `thoughts` (reasoning text).
- `code_agent.session.completed`
  - Purpose: code agent session ended.
  - Payload: `completion_reason` (`DONE` | `FAIL` | budget exhaustion label), `steps_executed` (int), `budget` (int), `summary` (LLM-written summary).
- `grounding.generate_coords.started`
  - Purpose: grounding model invoked for a referring expression.
  - Payload: `ref_expr` (string).
- `grounding.generate_coords.completed`
  - Purpose: grounding model returned screen coordinates.
  - Payload: `ref_expr` (string), `coords` ([x, y] ints), `source` (`custom_inference` | `service` | `llm`).
- `grounding.generate_coords.service_failed`
  - Purpose: all external grounding service retries failed.
  - Payload: `attempts` (int attempts tried), `prompt` (string sent to service).
- `grounding.generate_text_coords.started`
  - Purpose: OCR-based text span grounding started.
  - Payload: `phrase` (string), `alignment` (`center` default | `start` | `end`).
- `grounding.generate_text_coords.completed`
  - Purpose: OCR-based text span grounding finished.
  - Payload: `phrase` (string), `alignment` (as above), `coords` ([x, y] ints).
- `behavior_narrator.completed`
  - Purpose: behavior narrator finished captioning a screenshot pair.
  - Payload: `step` (int), `action` (pyautogui action text), `thoughts` (LLM reasoning), `caption` (fact-style description). Often aligns with `runner.step.behavior`.

## MCP Agent
- `mcp.task.started`
  - Purpose: MCP agent run began.
  - Payload: `task` (first 100 chars), `user_id` (normalized), `step_id` (orchestrator step binding), `tool_constraints` (dict or null).
- `mcp.task.completed`
  - Purpose: MCP agent run finished.
  - Payload: `success` (boolean), `step_id` (string).
- `mcp.planner.failed`
  - Purpose: planner failed to produce a valid command.
  - Payload: `reason` (error code string), `llm_preview` (first 200 chars of bad output).
- `mcp.llm.completed`
  - Purpose: planner LLM call succeeded.
  - Payload: `model` (string), `output_chars` (int length of assistant text).
- `mcp.action.planned`
  - Purpose: planner selected a tool to call.
  - Payload: `provider` (string), `tool` (resolved tool name).
- `mcp.action.started`
  - Purpose: low-level tool invocation dispatched.
  - Payload: `server` (provider), `tool` (tool id), `payload_keys` (list of argument keys), `user_id` (string).
- `mcp.action.failed`
  - Purpose: tool invocation threw/returned an error.
  - Payload: `server` (provider), `tool` (tool id), `error` (string), `user_id` (string).
- `mcp.action.completed`
  - Purpose: tool invocation completed; emitted both at executor layer and transport layer.
  - Payload shapes:
    - Executor: `provider`, `tool` (resolved tool name).
    - Transport: `server`, `tool`, `user_id`.
- `mcp.sandbox.run`
  - Purpose: sandbox code execution finished.
  - Payload: `success` (bool), `timed_out` (bool), `log_lines` (int), `code_preview` (first 200 chars), `label` (sandbox name).
- `mcp.observation_processor.completed`
  - Purpose: large tool/sandbox output was compressed.
  - Payload: `type` (string label), `original_tokens` (int), `compressed_tokens` (int), `reduction_percent` (float), `target_tokens` (int).
- `mcp.summary.created`
  - Purpose: a summary artifact was generated for storage/redaction.
  - Payload: `label` (string), `purpose` (string), `truncated` (bool or null).
- `mcp.high_signal`
  - Purpose: surfaced key fields from a tool result for UI.
  - Payload: on success `{provider, tool, success: true, signals: {…}}`; on failure `{provider, tool, success: false, error}`.
