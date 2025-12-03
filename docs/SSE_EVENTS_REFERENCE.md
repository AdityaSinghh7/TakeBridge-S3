# SSE Events Reference Guide

This document provides a comprehensive overview of all Server-Sent Events (SSE) emitted by the backend during AI agent loop execution. These events enable real-time progress tracking and status updates on the frontend.

## Table of Contents

1. [SSE Format](#sse-format)
2. [Event Categories](#event-categories)
3. [Event Reference](#event-reference)
4. [Frontend Integration](#frontend-integration)

---

## SSE Format

All SSE events follow the standard Server-Sent Events format:

```
event: <event_name>
data: <json_payload>

```

The `data` field contains a JSON object with event-specific information.

---

## Event Categories

SSE events are organized into the following categories:

1. **Response Lifecycle Events** - High-level orchestration flow
2. **Orchestrator Events** - Top-level planning and coordination
3. **MCP Agent Events** - MCP (Model Context Protocol) agent execution
4. **Computer Use Agent Events** - GUI automation and computer interaction
5. **Code Agent Events** - Code execution and scripting
6. **Grounding Agent Events** - UI element detection and coordinate generation
7. **LLM Stream Events** - Real-time LLM reasoning and output streaming
8. **Action Events** - Tool invocations and MCP actions
9. **System Events** - Keepalive and error handling

---

## Event Reference

### 1. Response Lifecycle Events

These events track the overall request lifecycle from start to completion.

#### `response.created`
**When:** Immediately when the SSE stream is initialized  
**Payload:**
```json
{
  "status": "accepted",
  "workspace": {  // Optional, if workspace context provided
    "id": "...",
    "controller_base_url": "...",
    "vnc_url": "..."
  }
}
```
**Frontend Use:** Show initial loading state, display workspace info if available

---

#### `response.in_progress`
**When:** Right after stream initialization, before agent execution starts  
**Payload:**
```json
{
  "status": "running"
}
```
**Frontend Use:** Update UI to show task is actively running

---

#### `response`
**When:** When the orchestration completes successfully  
**Payload:**
```json
{
  "task": "original task string",
  "status": "success" | "partial",
  "completion_reason": "ok" | "no_steps",
  "steps": [
    {
      "step_id": "...",
      "target": "mcp" | "computer_use",
      "status": "completed" | "failed",
      "success": true | false,
      "output": {...},
      "error": "...",  // if failed
      "started_at": "...",
      "finished_at": "..."
    }
  ]
}
```
**Frontend Use:** Display final results, show step-by-step breakdown

---

#### `response.completed`
**When:** Final completion event, sent after `response` event  
**Payload:**
```json
{
  "status": "success" | "partial" | "completed",
  "completion_reason": "ok" | "no_steps" | "clean_exit"
}
```
**Frontend Use:** Mark task as complete, enable user actions

---

#### `response.failed`
**When:** If orchestration fails with an exception  
**Payload:**
```json
{
  "error": "error message string"
}
```
**Frontend Use:** Display error message to user

---

#### `error`
**When:** General error during execution  
**Payload:**
```json
{
  "error": "error message string"
}
```
**Frontend Use:** Show error notification

---

### 2. Orchestrator Events

These events track the high-level orchestrator's planning and step coordination.

#### `orchestrator.task.started`
**When:** When orchestrator begins processing a task  
**Payload:**
```json
{
  "request_id": "...",
  "tenant_id": "...",
  "task": "task description (first 100 chars)",
  "max_steps": 10,
  "tool_constraints": {  // Optional
    "mode": "auto" | "custom",
    "providers": [...],
    "tools": [...]
  }
}
```
**Frontend Use:** Show task initialization, display constraints

---

#### `orchestrator.planning.completed`
**When:** After orchestrator LLM decides next action  
**Payload:**
```json
{
  "decision_type": "next_step" | "task_complete" | "task_impossible",
  "target": "mcp" | "computer_use",  // if decision_type is "next_step"
  "task_preview": "next step description (first 80 chars)"  // if decision_type is "next_step"
}
```
**Frontend Use:** Show planning status, indicate which agent will execute next

---

#### `orchestrator.step.dispatching`
**When:** When orchestrator dispatches a step to an agent  
**Payload:**
```json
{
  "step_id": "step-0",
  "target": "mcp" | "computer_use",
  "task": "step description (first 100 chars)"
}
```
**Frontend Use:** Show which step is being executed and by which agent

---

#### `orchestrator.step.completed`
**When:** When a step finishes execution  
**Payload:**
```json
{
  "step_id": "step-0",
  "status": "completed" | "failed",
  "success": true | false
}
```
**Frontend Use:** Update step status in UI, show success/failure indicator

---

#### `orchestrator.task.completed`
**When:** When entire orchestrator task completes  
**Payload:**
```json
{
  "total_steps": 3,
  "status": "success" | "partial"
}
```
**Frontend Use:** Show final summary, total steps executed

---

### 3. MCP Agent Events

These events track the MCP (Model Context Protocol) agent's execution flow.

#### `mcp.task.started`
**When:** When MCP agent begins processing a task  
**Payload:**
```json
{
  "task": "task description (first 100 chars)",
  "user_id": "normalized_user_id",
  "step_id": "mcp-main",
  "tool_constraints": {...}  // Optional
}
```
**Frontend Use:** Show MCP agent initialization

---

#### `mcp.planner.started`
**When:** When MCP planner loop begins  
**Payload:**
```json
{
  "task": "full task string",
  "user_id": "normalized_user_id",
  "budget": {
    "max_steps": 20,
    "max_tool_calls": 50,
    "max_code_runs": 10,
    "max_llm_cost_usd": 1.0
  },
  "extra_context_keys": ["key1", "key2"],
  "ephemeral_toolbox": "/tmp/toolbox-...",
  "tool_constraints": {...}  // Optional
}
```
**Frontend Use:** Show planner initialization, display budget limits

---

#### `mcp.search.completed`
**When:** After tool search completes  
**Payload:**
```json
{
  "query": "search query string",
  "detail_level": "full",
  "result_count": 5,
  "tool_ids": ["gmail.gmail_search", "gmail.gmail_send_email"]
}
```
**Frontend Use:** Show search results, display found tools

---

#### `mcp.budget.exceeded`
**When:** When MCP agent hits budget limits  
**Payload:**
```json
{
  "budget_type": "max_steps" | "max_tool_calls" | "max_code_runs" | "max_llm_cost_usd",
  "cost": 0.85,
  "steps_taken": 20,
  "model": "o4-mini"  // Optional
}
```
**Frontend Use:** Show budget exceeded warning, explain why task stopped

---

#### `mcp.planner.failed`
**When:** When planner encounters a fatal error  
**Payload:**
```json
{
  "reason": "error_code",
  "llm_preview": "preview of LLM response (first 200 chars)"
}
```
**Frontend Use:** Show planner failure, display error details

---

#### `mcp.task.completed`
**When:** When MCP task completes  
**Payload:**
```json
{
  "success": true | false,
  "step_id": "mcp-main"
}
```
**Frontend Use:** Mark MCP task as complete

---

#### `mcp.toolbox.generated`
**When:** When MCP toolbox manifest is generated  
**Payload:**
```json
{
  "user_id": "...",
  "providers": 5,
  "persisted": false,
  "fingerprint": "...",
  "tool_constraints": {...}  // Optional
}
```
**Frontend Use:** Show toolbox initialization (usually not needed for UI)

---

### 4. Computer Use Agent Events

These events track the computer use agent (GUI automation) execution.

#### `runner.started`
**When:** When computer use runner begins  
**Payload:**
```json
{
  "task": "task description",
  "max_steps": 20,
  "platform": "macos" | "windows" | "linux"
}
```
**Frontend Use:** Show runner initialization, display platform

---

#### `runner.step.started`
**When:** At the start of each runner step  
**Payload:**
```json
{
  "step": 1
}
```
**Frontend Use:** Update step counter, show current step number

---

#### `runner.step.agent_response`
**When:** After agent generates plan/action for a step  
**Payload:**
```json
{
  "step": 1,
  "action": "pyautogui.click(100, 200)",
  "exec_code": "pyautogui.click(100, 200)",
  "normalized_action": "CLICK",
  "info": {
    "plan": "I will click on the button",
    "reflection": "The click was successful",
    "reflection_thoughts": "User saw expected result",
    "code_agent_output": {...}  // Optional, if code agent was used
  }
}
```
**Frontend Use:** Show agent's plan and action, display reasoning

---

#### `runner.step.execution.started`
**When:** When step execution begins  
**Payload:**
```json
{
  "step": 1,
  "mode": "controller_execute" | "wait" | "final_screenshot" | "failure_screenshot" | "noop",
  "exec_code": "pyautogui.click(100, 200)"  // if mode is "controller_execute"
}
```
**Frontend Use:** Show execution mode, indicate what's happening

---

#### `runner.step.execution.completed`
**When:** When step execution finishes  
**Payload:**
```json
{
  "step": 1,
  "mode": "controller_execute" | "wait" | "final_screenshot" | "failure_screenshot" | "noop",
  "did_click": true | false,  // if mode is "controller_execute"
  "result": {...}  // Optional, execution result details
}
```
**Frontend Use:** Show execution result, update UI

---

#### `runner.step.behavior`
**When:** After behavior narrator analyzes step  
**Payload:**
```json
{
  "step": 1,
  "fact_answer": "The button was clicked successfully",
  "fact_thoughts": "Analysis of what happened"
}
```
**Frontend Use:** Show behavior analysis, explain what happened

---

#### `runner.step.completed`
**When:** When a step fully completes  
**Payload:**
```json
{
  "step": 1,
  "status": "in_progress" | "success" | "failed",
  "action": "pyautogui.click(100, 200)",
  "completion_reason": "DONE" | "FAIL" | null
}
```
**Frontend Use:** Update step status, show completion reason if terminal

---

#### `runner.completed`
**When:** When runner finishes all steps  
**Payload:**
```json
{
  "status": "success" | "failed" | "timeout",
  "completion_reason": "DONE" | "FAIL" | "MAX_STEPS_REACHED",
  "steps": 5
}
```
**Frontend Use:** Show final runner status, display total steps

---

### 5. Code Agent Events

These events track the code agent's execution when it's invoked for code-based tasks.

#### `code_agent.session.started`
**When:** When code agent session begins  
**Payload:**
```json
{
  "task": "task instruction",
  "budget": 20
}
```
**Frontend Use:** Show code agent initialization

---

#### `code_agent.step.started`
**When:** At the start of each code agent step  
**Payload:**
```json
{
  "step": 1,
  "budget_remaining": 19
}
```
**Frontend Use:** Show code agent step progress

---

#### `code_agent.step.response`
**When:** After code agent generates code for a step  
**Payload:**
```json
{
  "step": 1,
  "action": "```python\ncode here\n```",
  "thoughts": "agent's reasoning"
}
```
**Frontend Use:** Display generated code, show agent reasoning

---

#### `code_agent.step.execution`
**When:** After code execution completes  
**Payload:**
```json
{
  "step": 1,
  "code_type": "python" | "bash" | null,
  "status": "success" | "error" | "skipped",
  "output": "stdout output",
  "error": "stderr output",
  "message": "status message",
  "return_code": 0
}
```
**Frontend Use:** Show code execution results, display output/errors

---

#### `code_agent.step.completed`
**When:** When a code agent step finishes  
**Payload:**
```json
{
  "step": 1,
  "status": "success" | "error" | "skipped",
  "thoughts": "agent's reasoning"
}
```
**Frontend Use:** Update step status

---

#### `code_agent.session.completed`
**When:** When code agent session ends  
**Payload:**
```json
{
  "completion_reason": "DONE" | "FAIL" | "BUDGET_EXHAUSTED_AFTER_N_STEPS",
  "steps_executed": 5,
  "budget": 20,
  "summary": "execution summary"
}
```
**Frontend Use:** Show code agent completion, display summary

---

### 6. Grounding Agent Events

These events track UI element detection and coordinate generation.

#### `grounding.generate_coords.started`
**When:** When grounding begins to find coordinates  
**Payload:**
```json
{
  "ref_expr": "click on the submit button"
}
```
**Frontend Use:** Show grounding in progress

---

#### `grounding.generate_coords.service_attempt`
**When:** When attempting grounding service call  
**Payload:**
```json
{
  "attempt": 1,
  "prompt": "click on the submit button"
}
```
**Frontend Use:** Show retry attempts (usually not needed)

---

#### `grounding.generate_coords.service_success`
**When:** When grounding service succeeds  
**Payload:**
```json
{
  "attempt": 1,
  "coords": [500, 300]
}
```
**Frontend Use:** Show successful coordinate detection

---

#### `grounding.generate_coords.service_retry`
**When:** When grounding service retries after failure  
**Payload:**
```json
{
  "attempt": 1,
  "error": "error message"
}
```
**Frontend Use:** Show retry status (usually not needed)

---

#### `grounding.generate_coords.service_fallback`
**When:** When falling back from service to LLM grounding  
**Payload:**
```json
{
  "ref_expr": "click on the submit button"
}
```
**Frontend Use:** Show fallback status (usually not needed)

---

#### `grounding.generate_coords.service_failed`
**When:** When all grounding service attempts fail  
**Payload:**
```json
{
  "attempts": 3,
  "prompt": "click on the submit button"
}
```
**Frontend Use:** Show service failure (usually not needed)

---

#### `grounding.generate_coords.completed`
**When:** When coordinate generation completes  
**Payload:**
```json
{
  "ref_expr": "click on the submit button",
  "coords": [500, 300],
  "source": "service" | "llm" | "custom_inference"
}
```
**Frontend Use:** Show detected coordinates, indicate source

---

#### `grounding.generate_text_coords.started`
**When:** When text-based coordinate generation begins  
**Payload:**
```json
{
  "phrase": "Submit",
  "alignment": "center" | "start" | "end"
}
```
**Frontend Use:** Show text grounding in progress

---

#### `grounding.generate_text_coords.completed`
**When:** When text coordinate generation completes  
**Payload:**
```json
{
  "phrase": "Submit",
  "alignment": "center" | "start" | "end",
  "coords": [500, 300]
}
```
**Frontend Use:** Show detected text coordinates

---

### 7. LLM Stream Events

These events provide real-time streaming of LLM reasoning and output.

#### `<source>.started`
**When:** When an LLM call begins  
**Payload:**
```json
{
  "attempt": 1,
  "temperature": 0.0,
  "use_thinking": false
}
```
**Example:** `orchestrator.planning.started`, `code_agent.step_1.started`  
**Frontend Use:** Show LLM call in progress

---

#### `<source>.reasoning.delta`
**When:** Real-time chunks of LLM reasoning text  
**Payload:**
```json
{
  "source": "code_agent.step_1",
  "text": "chunk of reasoning text"
}
```
**Frontend Use:** Stream reasoning text in real-time, show "thinking" indicator

---

#### `<source>.output.delta`
**When:** Real-time chunks of LLM output text  
**Payload:**
```json
{
  "source": "code_agent.step_1",
  "text": "chunk of output text"
}
```
**Frontend Use:** Stream output text in real-time, show progressive response

---

#### `<source>.completed`
**When:** When LLM call completes  
**Payload:**
```json
{
  "attempts": 1,
  "text": "full response text",
  "model": "o4-mini",
  "thoughts": "reasoning text",  // Optional
  "answer": "extracted answer",  // Optional
  "streamed_thoughts": "...",  // Optional
  "streamed_output": "..."  // Optional
}
```
**Frontend Use:** Show final response, display model used

---

#### `<source>.failed`
**When:** When LLM call fails after retries  
**Payload:**
```json
{
  "attempts": 3,
  "error": "error message"
}
```
**Frontend Use:** Show LLM failure, display error

---

#### `<source>.stream.completed`
**When:** When LLM stream completes  
**Payload:**
```json
{
  "source": "code_agent.step_1"
}
```
**Frontend Use:** Mark stream as complete

---

#### `<source>.stream.error`
**When:** When LLM stream encounters an error  
**Payload:**
```json
{
  "source": "code_agent.step_1",
  "error": {...}
}
```
**Frontend Use:** Show stream error

---

### 8. Action Events

These events track MCP tool invocations and actions.

#### `mcp.action.started`
**When:** When an MCP action/tool invocation begins  
**Payload:**
```json
{
  "server": "gmail",
  "tool": "gmail_search",
  "payload_keys": ["query", "max_results"],
  "user_id": "..."
}
```
**Frontend Use:** Show tool invocation in progress

---

#### `mcp.action.transport`
**When:** When action transport method is selected  
**Payload:**
```json
{
  "server": "gmail",
  "tool": "gmail_search",
  "transport": "mcp_stream" | "composio_execute_api",
  "user_id": "..."
}
```
**Frontend Use:** Show transport method (usually not needed)

---

#### `mcp.action.request`
**When:** When making request to Composio execute API  
**Payload:**
```json
{
  "server": "gmail",
  "tool": "gmail_search",
  "transport": "composio_execute_api",
  "url": "https://...",
  "user_id": "..."
}
```
**Frontend Use:** Show API request (usually not needed)

---

#### `mcp.action.completed`
**When:** When MCP action completes successfully  
**Payload:**
```json
{
  "server": "gmail",
  "tool": "gmail_search",
  "user_id": "..."
}
```
**Frontend Use:** Show successful tool execution

---

#### `mcp.action.failed`
**When:** When MCP action fails  
**Payload:**
```json
{
  "server": "gmail",
  "tool": "gmail_search",
  "error": "error message",
  "user_id": "..."
}
```
**Frontend Use:** Show tool execution failure, display error

---

### 9. System Events

These events handle system-level concerns like keepalive and errors.

#### `server.keepalive`
**When:** Periodic keepalive (every 15 seconds)  
**Payload:**
```json
{
  "ts": 1234567890.123
}
```
**Frontend Use:** Keep connection alive, show connection is active

---

#### `server.keepalive.stopped`
**When:** When keepalive task stops  
**Payload:**
```json
{
  "ts": 1234567890.123
}
```
**Frontend Use:** Indicate keepalive stopped (usually not needed)

---

## Frontend Integration

### Basic SSE Parser

```typescript
async function* parseSSE(stream: ReadableStream<Uint8Array>) {
  const decoder = new TextDecoder();
  const reader = stream.getReader();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Split on double newline (SSE frame boundary)
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        // Parse SSE frame
        const lines = frame.split('\n');
        let event = 'message';
        let data = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            event = line.slice(7);
          } else if (line.startsWith('data: ')) {
            data += line.slice(6);
          }
        }

        if (data) {
          try {
            yield { event, data: JSON.parse(data) };
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }

        boundary = buffer.indexOf('\n\n');
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

### Event Handler Example

```typescript
async function handleTaskExecution(task: string, userId: string) {
  const res = await fetch('/orchestrate/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify({ task }),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Failed to start task: ${res.status}`);
  }

  for await (const { event, data } of parseSSE(res.body)) {
    switch (event) {
      case 'response.created':
        // Show initial loading state
        updateUI({ status: 'initializing', workspace: data.workspace });
        break;

      case 'response.in_progress':
        // Show running state
        updateUI({ status: 'running' });
        break;

      case 'orchestrator.task.started':
        // Show task started
        updateUI({ 
          status: 'running',
          task: data.task,
          maxSteps: data.max_steps 
        });
        break;

      case 'orchestrator.planning.completed':
        // Show planning decision
        updateUI({ 
          planning: {
            decision: data.decision_type,
            target: data.target,
            task: data.task_preview
          }
        });
        break;

      case 'orchestrator.step.dispatching':
        // Show step being dispatched
        addStep({
          id: data.step_id,
          target: data.target,
          task: data.task,
          status: 'pending'
        });
        break;

      case 'orchestrator.step.completed':
        // Update step status
        updateStep(data.step_id, {
          status: data.status,
          success: data.success
        });
        break;

      case 'runner.step.started':
        // Show runner step
        updateUI({ currentStep: data.step });
        break;

      case 'runner.step.agent_response':
        // Show agent's plan and action
        updateStep(data.step, {
          plan: data.info.plan,
          action: data.action,
          reflection: data.info.reflection
        });
        break;

      case 'code_agent.step.response':
        // Show code agent's code
        updateStep(data.step, {
          code: data.action,
          thoughts: data.thoughts
        });
        break;

      case 'code_agent.step.execution':
        // Show code execution result
        updateStep(data.step, {
          execution: {
            status: data.status,
            output: data.output,
            error: data.error
          }
        });
        break;

      case 'response.completed':
        // Show completion
        updateUI({ 
          status: 'completed',
          completionReason: data.completion_reason
        });
        break;

      case 'response':
        // Show final results
        updateUI({ 
          status: 'completed',
          results: data.steps,
          finalStatus: data.status
        });
        break;

      case 'error':
      case 'response.failed':
        // Show error
        updateUI({ 
          status: 'error',
          error: data.error
        });
        break;

      case 'server.keepalive':
        // Connection is alive
        updateConnectionStatus('active');
        break;

      default:
        // Handle other events or log for debugging
        console.log('Unhandled event:', event, data);
    }
  }
}
```

### Progress Tracking Example

```typescript
interface ProgressState {
  status: 'idle' | 'initializing' | 'running' | 'completed' | 'error';
  currentStep?: number;
  totalSteps?: number;
  currentAgent?: 'orchestrator' | 'mcp' | 'computer_use' | 'code_agent';
  currentAction?: string;
  progress: number; // 0-100
}

function calculateProgress(event: string, data: any, state: ProgressState): number {
  // Calculate progress based on events
  if (event === 'response.created') return 5;
  if (event === 'orchestrator.task.started') return 10;
  if (event === 'orchestrator.step.dispatching') {
    const stepNum = parseInt(data.step_id.split('-')[1] || '0');
    return 10 + (stepNum / (state.totalSteps || 10)) * 80;
  }
  if (event === 'runner.step.started') {
    return 10 + (data.step / (state.totalSteps || 20)) * 80;
  }
  if (event === 'response.completed') return 100;
  return state.progress;
}
```

---

## Event Flow Diagram

```
User Request
    ↓
response.created
    ↓
response.in_progress
    ↓
orchestrator.task.started
    ↓
[Loop: For each step]
    ├─ orchestrator.planning.completed
    ├─ orchestrator.step.dispatching
    │   ├─ [If MCP Agent]
    │   │   ├─ mcp.task.started
    │   │   ├─ mcp.planner.started
    │   │   ├─ mcp.search.completed (if search)
    │   │   ├─ mcp.action.started/completed (if tool call)
    │   │   └─ mcp.task.completed
    │   │
    │   └─ [If Computer Use Agent]
    │       ├─ runner.started
    │       ├─ [For each step]
    │       │   ├─ runner.step.started
    │       │   ├─ runner.step.agent_response
    │       │   ├─ runner.step.execution.started
    │       │   ├─ runner.step.execution.completed
    │       │   ├─ runner.step.behavior
    │       │   └─ runner.step.completed
    │       │   ├─ [If code agent invoked]
    │       │   │   ├─ code_agent.session.started
    │       │   │   ├─ code_agent.step.started
    │       │   │   ├─ code_agent.step.response
    │       │   │   ├─ code_agent.step.execution
    │       │   │   └─ code_agent.step.completed
    │       │   │   └─ code_agent.session.completed
    │       │   └─ [If grounding needed]
    │       │       ├─ grounding.generate_coords.started
    │       │       └─ grounding.generate_coords.completed
    │       └─ runner.completed
    │
    └─ orchestrator.step.completed
    ↓
orchestrator.task.completed
    ↓
response
    ↓
response.completed
```

---

## Best Practices

1. **Handle All Events**: Even if you don't display all events, handle them gracefully to avoid errors
2. **Show Progress**: Use step events to show progress bars and step counters
3. **Stream LLM Output**: Use `.reasoning.delta` and `.output.delta` events for real-time streaming
4. **Error Handling**: Always handle `error` and `response.failed` events
5. **Keepalive**: Monitor `server.keepalive` to detect connection issues
6. **State Management**: Maintain UI state based on event sequence
7. **Debouncing**: For high-frequency events like `.delta`, consider debouncing UI updates
8. **Logging**: Log all events during development to understand the flow

---

## Notes

- All timestamps in events are Unix timestamps (seconds since epoch)
- Event names are sanitized to contain only alphanumeric characters, dashes, underscores, and dots
- The `data` field is always a JSON object, never a primitive value
- Some events may not always be present depending on the execution path
- LLM stream events (`<source>.reasoning.delta`, `<source>.output.delta`) provide real-time streaming but may not always be available depending on the LLM provider

