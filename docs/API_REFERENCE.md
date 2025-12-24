# TakeBridge Orchestrator API Reference

## Overview

The TakeBridge Orchestrator API provides endpoints for executing multi-agent orchestration tasks with support for MCP (Model Context Protocol) tool integration, computer use capabilities, and real-time streaming updates via Server-Sent Events (SSE).

**Base URL**: `http://localhost:8000` (or your deployed URL)

**Architecture**: Multi-agent orchestration with three specialized agents:
- **Orchestrator Agent**: High-level planning and coordination
- **MCP Agent**: Execution of MCP tools (OAuth-authorized integrations like Gmail, Slack, etc.)
- **Computer Use Agent**: GUI automation and code execution

---

## Table of Contents

1. [Authentication & Multi-Tenancy](#authentication--multi-tenancy)
2. [Endpoints](#endpoints)
   - [POST /orchestrate](#post-orchestrate)
   - [GET /orchestrate/stream](#get-orchestratestream)
   - [POST /orchestrate/stream](#post-orchestratestream)
   - [GET /config](#get-config)
3. [Data Types](#data-types)
4. [SSE Event Reference](#sse-event-reference)
5. [Frontend Integration Guide](#frontend-integration-guide)
6. [Error Handling](#error-handling)
7. [Examples](#examples)

---

## Authentication & Multi-Tenancy

### User Identification

The API supports multi-tenant usage through user identification:

**Header**: `X-User-Id` (optional)
```http
X-User-Id: user-123
```

**Fallback**: If `X-User-Id` is not provided, the API uses the `TB_DEFAULT_USER_ID` environment variable.

**Purpose**:
- Scopes OAuth authorizations to specific users
- Ensures tool access is per-user, not system-wide
- Enables usage tracking and quotas per user

### Tool Authorization

Tools are available based on OAuth authorization status:
- Only tools from **authorized** providers are available to each user
- Authorization is managed through the MCP OAuth flow
- Each user must individually authorize providers (Gmail, Slack, etc.)

---

## Endpoints

### POST /orchestrate

Execute a single orchestrator task without streaming (blocking, returns final result).

#### Request

**Method**: `POST`
**Path**: `/orchestrate`
**Content-Type**: `application/json`

**Headers**:
| Header | Required | Type | Description |
|--------|----------|------|-------------|
| `X-User-Id` | No | string | User identifier for multi-tenancy. Falls back to `TB_DEFAULT_USER_ID` env var. |

**Body**:
```json
{
  "task": "string (required)",
  "worker": {
    "max_steps": "number (optional, default: 10)",
    "enable_reflection": "boolean (optional, default: true)",
    "engine": "string (optional, default: 'claude-3-5-sonnet-20241022')"
  },
  "grounding": {
    "base_url": "string (optional)",
    "api_key": "string (optional)"
  },
  "controller": {
    "host": "string (optional, default: 'localhost')",
    "port": "number (optional, default: 5900)"
  },
  "tool_constraints": {
    "mode": "auto | custom (optional, default: 'auto')",
    "providers": ["string (optional, for custom mode)"],
    "tools": ["string (optional, reserved for future use)"]
  }
}
```

**Field Descriptions**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task` | string | **Yes** | - | Natural language description of the task to execute. Example: "Send an email to john@example.com about the quarterly report" |
| `worker.max_steps` | number | No | 10 | Maximum number of worker steps before auto-termination |
| `worker.enable_reflection` | boolean | No | true | Enable self-reflection after each worker step |
| `worker.engine` | string | No | claude-3-5-sonnet-20241022 | LLM model to use for worker agent |
| `grounding.base_url` | string | No | Auto-detected from `RUNPOD_ID` | Base URL for grounding/coordinate inference service |
| `grounding.api_key` | string | No | From `RUNPOD_API_KEY` env | API key for grounding service authentication |
| `controller.host` | string | No | localhost | VM controller hostname for GUI automation |
| `controller.port` | number | No | 5900 | VM controller port for GUI automation |
| `tool_constraints.mode` | string | No | auto | Tool filtering mode: `auto` (all authorized tools) or `custom` (specific providers) |
| `tool_constraints.providers` | string[] | No | [] | List of provider names to allow (e.g., `["gmail", "slack"]`). Only applies in `custom` mode. |
| `tool_constraints.tools` | string[] | No | [] | Reserved for future tool-level filtering (currently unused) |

#### Response

**Status**: `200 OK`
**Content-Type**: `application/json`

```json
{
  "task": "string",
  "status": "success | partial | failed",
  "completion_reason": "ok | no_steps | max_steps_reached | error",
  "steps": [
    {
      "step_id": "string",
      "target": "mcp | computer_use",
      "task": "string",
      "result": "string",
      "success": "boolean",
      "error": "string | null"
    }
  ]
}
```

**Response Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `task` | string | The original task description |
| `status` | string | Overall execution status: `success` (all steps succeeded), `partial` (some steps failed), `failed` (execution failed) |
| `completion_reason` | string | Reason for completion: `ok` (task completed successfully), `no_steps` (no steps executed), `max_steps_reached` (budget exhausted), `error` (execution error) |
| `steps` | array | Array of executed steps with results |
| `steps[].step_id` | string | Unique identifier for the step (e.g., `step-mcp-001`) |
| `steps[].target` | string | Which agent executed the step: `mcp` or `computer_use` |
| `steps[].task` | string | Task description for this specific step |
| `steps[].result` | string | Result or output from the step execution |
| `steps[].success` | boolean | Whether the step completed successfully |
| `steps[].error` | string \| null | Error message if step failed, null otherwise |

---

### GET /orchestrate/stream

Simple streaming endpoint that accepts only a task query parameter. For backward compatibility.

#### Request

**Method**: `GET`
**Path**: `/orchestrate/stream?task={task}`

**Query Parameters**:
| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `task` | **Yes** | string | URL-encoded task description |

**Example**:
```http
GET /orchestrate/stream?task=Send%20an%20email%20to%20john@example.com
```

#### Response

**Status**: `200 OK`
**Content-Type**: `text/event-stream`
**Headers**:
```http
Cache-Control: no-cache
X-Accel-Buffering: no
```

**Body**: Server-Sent Events stream (see [SSE Event Reference](#sse-event-reference))

**Limitations**:
- Cannot specify tool constraints
- Cannot provide user ID
- Uses default worker/grounding/controller configuration
- **Recommendation**: Use `POST /orchestrate/stream` for production

---

### POST /orchestrate/stream

Full-featured streaming endpoint with support for tool constraints, user identification, and configuration overrides.

#### Request

**Method**: `POST`
**Path**: `/orchestrate/stream`
**Content-Type**: `application/json`

**Headers**:
| Header | Required | Type | Description |
|--------|----------|------|-------------|
| `X-User-Id` | No | string | User identifier for multi-tenancy. Falls back to `TB_DEFAULT_USER_ID` env var. |

**Body**:
```json
{
  "task": "string (required)",
  "worker": {
    "max_steps": "number (optional, default: 10)",
    "enable_reflection": "boolean (optional, default: true)",
    "engine": "string (optional, default: 'claude-3-5-sonnet-20241022')"
  },
  "grounding": {
    "base_url": "string (optional)",
    "api_key": "string (optional)"
  },
  "controller": {
    "host": "string (optional, default: 'localhost')",
    "port": "number (optional, default: 5900)"
  },
  "tool_constraints": {
    "mode": "auto | custom (optional, default: 'auto')",
    "providers": ["string (optional, for custom mode)"],
    "tools": ["string (optional, reserved for future use)"]
  }
}
```

**Field descriptions are identical to [POST /orchestrate](#post-orchestrate)**

#### Response

**Status**: `200 OK`
**Content-Type**: `text/event-stream`
**Headers**:
```http
Cache-Control: no-cache
X-Accel-Buffering: no
```

**Body**: Server-Sent Events stream (see [SSE Event Reference](#sse-event-reference))

---

### GET /config

Retrieve default configuration values for orchestrator, worker, grounding, and controller.

#### Request

**Method**: `GET`
**Path**: `/config`

**No parameters required**

#### Response

**Status**: `200 OK`
**Content-Type**: `application/json`

```json
{
  "controller": {
    "host": "localhost",
    "port": 5900
  },
  "worker": {
    "max_steps": 10,
    "enable_reflection": true,
    "engine": "claude-3-5-sonnet-20241022"
  },
  "grounding": {
    "base_url": null,
    "api_key": null
  }
}
```

**Use Case**: Frontend can fetch defaults and merge user overrides before submitting requests.

---

## Data Types

### ToolConstraints

Controls which MCP tools are available during task execution.

```typescript
interface ToolConstraints {
  mode: "auto" | "custom";
  providers?: string[];
  tools?: string[];
}
```

**Modes**:

#### Auto Mode (Default)
```json
{
  "mode": "auto"
}
```
- Uses **all** tools from OAuth-authorized providers
- Multi-tenant safe (per-user authorization)
- No manual configuration required
- **Recommended for most use cases**

#### Custom Mode
```json
{
  "mode": "custom",
  "providers": ["gmail", "slack", "google_calendar"]
}
```
- Restricts to specific providers from allow list
- Only authorized providers in the list will be available
- Useful for:
  - Limiting tool scope for specific tasks
  - Cost control (reducing LLM context size)
  - Compliance requirements (only approved tools)

**Available Providers** (must be OAuth-authorized by user):
- `gmail` - Gmail email operations
- `slack` - Slack messaging and channel management
- `google_calendar` - Google Calendar event management
- `github` - GitHub repository operations
- `notion` - Notion workspace operations
- `linear` - Linear issue tracking
- `asana` - Asana project management
- `shopify` - Shopify e-commerce operations
- And more...

### Step Result

```typescript
interface StepResult {
  step_id: string;
  target: "mcp" | "computer_use";
  task: string;
  result: string;
  success: boolean;
  error: string | null;
}
```

---

## SSE Event Reference

### Event Stream Structure

Server-Sent Events follow this format:

```
event: {event_name}
data: {json_payload}

```

**Parsing in JavaScript**:
```javascript
const eventSource = new EventSource('/orchestrate/stream?task=...');

eventSource.addEventListener('orchestrator.task.started', (e) => {
  const data = JSON.parse(e.data);
  console.log('Task started:', data);
});
```

### Event Lifecycle

Events are emitted in this general order:

```
1. response.created
2. response.in_progress
3. [orchestrator events]
4. [agent-specific events - mcp or computer_use]
5. [server.keepalive - periodic during execution]
6. response
7. response.completed
```

**Error path**:
```
1. response.created
2. response.in_progress
3. [events until error]
4. response.failed
5. error
```

---

### Server Lifecycle Events

#### `response.created`
**When**: Immediately when streaming request is accepted
**Payload**:
```json
{
  "status": "accepted"
}
```
**Frontend Action**: Show "Request accepted" or initialize progress UI

---

#### `response.in_progress`
**When**: Before orchestration begins
**Payload**:
```json
{
  "status": "running"
}
```
**Frontend Action**: Show "Task running" status

---

#### `server.keepalive`
**When**: Every 15 seconds during execution
**Payload**:
```json
{
  "ts": 1732901234.567
}
```
**Frontend Action**: Update "last activity" timestamp, prevent timeout

---

#### `response`
**When**: After successful task completion, before `response.completed`
**Payload**:
```json
{
  "task": "Send an email to john@example.com",
  "status": "success",
  "completion_reason": "ok",
  "steps": [
    {
      "step_id": "step-mcp-001",
      "target": "mcp",
      "task": "Send email using gmail",
      "result": "Email sent successfully to john@example.com",
      "success": true,
      "error": null
    }
  ]
}
```
**Frontend Action**: Display final results, show summary

---

#### `response.completed`
**When**: Final event in successful execution
**Payload**:
```json
{
  "status": "success",
  "completion_reason": "ok"
}
```
**Possible `completion_reason` values**:
- `ok` - Task completed successfully
- `no_steps` - No steps were executed
- `max_steps_reached` - Budget limit reached
- `clean_exit` - Clean shutdown via signal

**Frontend Action**: Close stream, show "Completed" status

---

#### `response.failed`
**When**: Task execution failed
**Payload**:
```json
{
  "error": "Error message describing what went wrong"
}
```
**Frontend Action**: Show error state, display error message

---

#### `error`
**When**: Follows `response.failed` with same error details
**Payload**:
```json
{
  "error": "Error message describing what went wrong"
}
```
**Frontend Action**: Log error for debugging

---

### Orchestrator Events

#### `orchestrator.task.started`
**When**: Orchestrator begins processing task
**Payload**:
```json
{
  "request_id": "req-001",
  "task": "Send an email and schedule a meeting",
  "max_steps": 10,
  "tenant_id": "org-123"
}
```
**Frontend Action**: Show task details, initialize step counter

---

#### `orchestrator.planning.started`
**When**: Orchestrator begins planning next step
**Payload**:
```json
{
  "step_number": 1,
  "last_failed": false
}
```
**Frontend Action**: Show "Planning step N..." status

---

#### `orchestrator.planning.completed`
**When**: Orchestrator has decided on next step
**Payload**:
```json
{
  "decision_type": "next_step",
  "target": "mcp",
  "task_preview": "Send an email to john@example.com about the quarterly report"
}
```
**Possible `target` values**:
- `mcp` - Will execute using MCP agent (tool calls)
- `computer_use` - Will execute using computer use agent (GUI automation)

**Frontend Action**: Show "Dispatching to {target} agent..." with task preview
**Note**: `task_preview` is the full task string for the next step (not truncated)

---

#### `orchestrator.step.dispatching`
**When**: Before dispatching step to target agent
**Payload**:
```json
{
  "step_id": "step-mcp-001",
  "target": "mcp",
  "task": "Send email to john@example.com about quarterly report"
}
```
**Frontend Action**: Add step to UI, show "In progress" status

---

#### `orchestrator.step.completed`
**When**: After step execution finishes
**Payload**:
```json
{
  "step_id": "step-mcp-001",
  "status": "completed",
  "success": true,
  "result": "Email sent successfully",
  "error": null
}
```
**If failed**:
```json
{
  "step_id": "step-mcp-002",
  "status": "failed",
  "success": false,
  "result": "",
  "error": "Gmail API rate limit exceeded"
}
```
**Frontend Action**: Update step status, show result or error

---

#### `orchestrator.task.completed`
**When**: All orchestration is complete
**Payload**:
```json
{
  "status": "success",
  "total_steps": 3,
  "successful_steps": 3,
  "failed_steps": 0
}
```
**Frontend Action**: Show completion summary

---

### MCP Agent Events

These events are emitted when the orchestrator dispatches to the MCP agent.

#### `mcp.task.started`
**When**: MCP agent begins processing a step
**Payload**:
```json
{
  "task": "Send email to john@example.com",
  "user_id": "user-123",
  "step_id": "step-mcp-001",
  "tool_constraints": {
    "mode": "auto"
  }
}
```
**Frontend Action**: Show "MCP agent started" for this step

---

#### `mcp.toolbox.generated`
**When**: MCP agent has built the available toolbox
**Payload**:
```json
{
  "tool_count": 47,
  "providers": ["gmail", "slack", "google_calendar"],
  "cache_hit": false
}
```
**Frontend Action**: Show available tool count and providers

---

#### `mcp.tool.search`
**When**: MCP agent is searching for relevant tools
**Payload**:
```json
{
  "query": "send email",
  "top_k": 5
}
```
**Frontend Action**: Show "Searching tools: {query}"

---

#### `mcp.tool.selected`
**When**: MCP agent has selected a tool to use
**Payload**:
```json
{
  "tool": "gmail_send_message",
  "provider": "gmail",
  "description": "Send an email message"
}
```
**Frontend Action**: Show "Using tool: {tool}" with provider badge

---

#### `mcp.tool.execution`
**When**: MCP agent is executing a tool
**Payload**:
```json
{
  "tool": "gmail_send_message",
  "params": {
    "to": "john@example.com",
    "subject": "Quarterly Report",
    "body": "Please find attached..."
  },
  "success": true,
  "result": "Message sent successfully"
}
```
**If failed**:
```json
{
  "tool": "gmail_send_message",
  "params": { ... },
  "success": false,
  "error": "Authentication failed"
}
```
**Frontend Action**: Show tool execution result

---

#### `mcp.task.completed`
**When**: MCP agent has finished processing the step
**Payload**:
```json
{
  "step_id": "step-mcp-001",
  "success": true,
  "result": "Email sent successfully to john@example.com"
}
```
**Frontend Action**: Update step with final result

---

### Computer Use Agent Events

These events are emitted when the orchestrator dispatches to the computer use agent.

#### `computer_use.task.started`
**When**: Computer use agent begins processing a step
**Payload**:
```json
{
  "task": "Open calendar and create event",
  "step_id": "step-cu-001",
  "controller": {
    "host": "localhost",
    "port": 5900
  }
}
```
**Frontend Action**: Show "Computer use agent started"

---

#### `worker.step.started`
**When**: Worker begins a new interaction step
**Payload**:
```json
{
  "step": 1,
  "turn_count": 0,
  "max_steps": 10
}
```
**Frontend Action**: Show "Worker step 1/10"

---

#### `worker.reflection.started`
**When**: Worker is performing self-reflection
**Payload**:
```json
{
  "step": 1,
  "has_prior_reflection": false
}
```
**Frontend Action**: Show "Reflecting on progress..."

---

#### `worker.step.completed`
**When**: Worker step finishes
**Payload**:
```json
{
  "step": 1,
  "plan": "Click on calendar icon in taskbar",
  "has_reflection": true,
  "action_type": "click"
}
```
**Frontend Action**: Show worker action summary

---

#### `code_agent.session.started`
**When**: Code agent begins a coding session
**Payload**:
```json
{
  "task": "Extract data from spreadsheet",
  "budget": 20
}
```
**Frontend Action**: Show "Code agent session started"

---

#### `code_agent.step.started`
**When**: Code agent begins a coding step
**Payload**:
```json
{
  "step": 1,
  "budget_remaining": 19
}
```
**Frontend Action**: Show "Code step 1, budget: 19"

---

#### `code_agent.session.completed`
**When**: Code agent session finishes
**Payload**:
```json
{
  "completion_reason": "DONE",
  "steps_executed": 5,
  "summary": "Successfully extracted data and saved to CSV"
}
```
**Possible `completion_reason` values**:
- `DONE` - Task completed successfully
- `MAX_STEPS_REACHED` - Budget exhausted
- `ERROR` - Execution error

**Frontend Action**: Show code session summary

---

#### `grounding.generate_coords.started`
**When**: Grounding agent begins coordinate inference
**Payload**:
```json
{
  "ref_expr": "the submit button"
}
```
**Frontend Action**: Show "Finding UI element: {ref_expr}"

---

#### `grounding.generate_coords.completed`
**When**: Grounding agent finishes coordinate inference
**Payload**:
```json
{
  "ref_expr": "the submit button",
  "coords": [450, 680],
  "method": "llm_inference"
}
```
**Frontend Action**: Show "Located element at ({x}, {y})"

---

#### `grounding.code_agent.started`
**When**: Grounding uses code agent for coordinate finding
**Payload**:
```json
{
  "ref_expr": "all email addresses on the page"
}
```
**Frontend Action**: Show "Using code agent for grounding"

---

#### `computer_use.task.completed`
**When**: Computer use agent finishes the step
**Payload**:
```json
{
  "step_id": "step-cu-001",
  "success": true,
  "result": "Calendar event created successfully"
}
```
**Frontend Action**: Update step with final result

---

## Frontend Integration Guide

### Basic EventSource Setup

```javascript
async function executeTask(task, toolConstraints = null) {
  const response = await fetch('/orchestrate/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getCurrentUserId(), // Your user ID logic
    },
    body: JSON.stringify({
      task,
      tool_constraints: toolConstraints,
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop(); // Keep incomplete event in buffer

    for (const line of lines) {
      if (line.startsWith('event:')) {
        const [eventLine, dataLine] = line.split('\n');
        const event = eventLine.replace('event: ', '');
        const data = JSON.parse(dataLine.replace('data: ', ''));

        handleEvent(event, data);
      }
    }
  }
}

function handleEvent(event, data) {
  console.log(`Event: ${event}`, data);

  // Route to specific handlers
  switch (event) {
    case 'orchestrator.task.started':
      onTaskStarted(data);
      break;
    case 'orchestrator.step.dispatching':
      onStepDispatching(data);
      break;
    case 'orchestrator.step.completed':
      onStepCompleted(data);
      break;
    case 'mcp.tool.execution':
      onToolExecution(data);
      break;
    case 'response.completed':
      onResponseCompleted(data);
      break;
    // ... handle other events
  }
}
```

### React Hook Example

```typescript
import { useEffect, useState } from 'react';

interface OrchestratorEvent {
  event: string;
  data: any;
}

interface OrchestratorState {
  status: 'idle' | 'running' | 'completed' | 'failed';
  events: OrchestratorEvent[];
  currentStep: string | null;
  error: string | null;
}

export function useOrchestrator(task: string, userId: string) {
  const [state, setState] = useState<OrchestratorState>({
    status: 'idle',
    events: [],
    currentStep: null,
    error: null,
  });

  useEffect(() => {
    if (!task) return;

    setState((prev) => ({ ...prev, status: 'running' }));

    const controller = new AbortController();

    fetch('/orchestrate/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
      },
      body: JSON.stringify({ task }),
      signal: controller.signal,
    })
      .then((response) => response.body)
      .then((body) => {
        const reader = body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function readStream() {
          reader.read().then(({ done, value }) => {
            if (done) {
              setState((prev) => ({ ...prev, status: 'completed' }));
              return;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (line.startsWith('event:')) {
                const [eventLine, dataLine] = line.split('\n');
                const event = eventLine.replace('event: ', '');
                const data = JSON.parse(dataLine.replace('data: ', ''));

                setState((prev) => ({
                  ...prev,
                  events: [...prev.events, { event, data }],
                }));

                // Handle specific events
                if (event === 'orchestrator.step.dispatching') {
                  setState((prev) => ({
                    ...prev,
                    currentStep: data.step_id,
                  }));
                }

                if (event === 'response.failed') {
                  setState((prev) => ({
                    ...prev,
                    status: 'failed',
                    error: data.error,
                  }));
                }
              }
            }

            readStream();
          });
        }

        readStream();
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setState((prev) => ({
            ...prev,
            status: 'failed',
            error: error.message,
          }));
        }
      });

    return () => {
      controller.abort();
    };
  }, [task, userId]);

  return state;
}
```

### UI Component Example

```typescript
function TaskExecutor({ task, userId }) {
  const { status, events, currentStep, error } = useOrchestrator(task, userId);

  const orchestratorEvents = events.filter((e) =>
    e.event.startsWith('orchestrator.')
  );
  const mcpEvents = events.filter((e) => e.event.startsWith('mcp.'));
  const cuEvents = events.filter((e) =>
    e.event.startsWith('worker.') ||
    e.event.startsWith('code_agent.') ||
    e.event.startsWith('grounding.')
  );

  return (
    <div className="task-executor">
      <div className="status">
        Status: {status}
        {currentStep && ` (${currentStep})`}
      </div>

      {error && (
        <div className="error">
          Error: {error}
        </div>
      )}

      <div className="events">
        <h3>Orchestrator Events</h3>
        {orchestratorEvents.map((e, i) => (
          <EventCard key={i} event={e.event} data={e.data} />
        ))}

        <h3>MCP Agent Events</h3>
        {mcpEvents.map((e, i) => (
          <EventCard key={i} event={e.event} data={e.data} />
        ))}

        <h3>Computer Use Events</h3>
        {cuEvents.map((e, i) => (
          <EventCard key={i} event={e.event} data={e.data} />
        ))}
      </div>
    </div>
  );
}
```

### Recommended Event Handling Strategy

1. **Group events by agent**: Separate orchestrator, MCP, and computer use events for clearer UI
2. **Track step lifecycle**: Use `orchestrator.step.dispatching` and `orchestrator.step.completed` to show step progress
3. **Show tool usage**: Highlight `mcp.tool.selected` and `mcp.tool.execution` for transparency
4. **Progress indicators**: Use `worker.step.started` and step counts for progress bars
5. **Error states**: Always handle `response.failed` and `error` events
6. **Keepalive**: Use `server.keepalive` to show "last activity" timestamp

---

## Error Handling

### HTTP Error Responses

#### 400 Bad Request
**When**: Invalid request payload
**Response**:
```json
{
  "detail": "Validation error: task field is required"
}
```
**Frontend Action**: Validate payload before sending, show validation errors

---

#### 500 Internal Server Error
**When**: Server-side execution error
**Response**:
```json
{
  "detail": "Orchestration failed: Database connection timeout"
}
```
**Frontend Action**: Show generic error message, log for debugging

---

### SSE Error Events

#### `response.failed`
**When**: Task execution fails during streaming
**Payload**:
```json
{
  "error": "MCP agent crashed: Out of memory"
}
```
**Frontend Action**: Stop showing progress, display error state

---

#### `error`
**When**: Follows `response.failed`
**Payload**: Same as `response.failed`
**Frontend Action**: Log for debugging

---

### Network Errors

**Connection Lost**:
```javascript
eventSource.onerror = (error) => {
  console.error('EventSource error:', error);
  // Show "Connection lost" message
  // Implement retry logic if needed
};
```

**Timeout**:
- Monitor `server.keepalive` events
- If no keepalive for > 30 seconds, consider connection dead
- Implement reconnection logic

---

## Examples

### Example 1: Simple Email Task

**Request**:
```bash
curl -X POST http://localhost:8000/orchestrate/stream \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-123" \
  -d '{
    "task": "Send an email to john@example.com with subject \"Meeting Tomorrow\" and body \"Let'\''s meet at 2pm\""
  }'
```

**Event Sequence**:
```
event: response.created
data: {"status":"accepted"}

event: response.in_progress
data: {"status":"running"}

event: orchestrator.task.started
data: {"request_id":"req-001","task":"Send an email...","max_steps":10}

event: orchestrator.planning.started
data: {"step_number":1,"last_failed":false}

event: orchestrator.planning.completed
data: {"decision_type":"next_step","target":"mcp","task_preview":"Send an email to john@example.com about the quarterly report"}

event: orchestrator.step.dispatching
data: {"step_id":"step-mcp-001","target":"mcp","task":"Send email to john@example.com..."}

event: mcp.task.started
data: {"task":"Send email...","user_id":"user-123","step_id":"step-mcp-001"}

event: mcp.toolbox.generated
data: {"tool_count":47,"providers":["gmail","slack"],"cache_hit":false}

event: mcp.tool.selected
data: {"tool":"gmail_send_message","provider":"gmail","description":"Send email"}

event: mcp.tool.execution
data: {"tool":"gmail_send_message","params":{...},"success":true,"result":"Message sent"}

event: mcp.task.completed
data: {"step_id":"step-mcp-001","success":true,"result":"Email sent successfully"}

event: orchestrator.step.completed
data: {"step_id":"step-mcp-001","status":"completed","success":true}

event: orchestrator.task.completed
data: {"status":"success","total_steps":1,"successful_steps":1}

event: response
data: {"task":"Send an email...","status":"success","completion_reason":"ok","steps":[...]}

event: response.completed
data: {"status":"success","completion_reason":"ok"}
```

---

### Example 2: Custom Tool Constraints

**Request**:
```bash
curl -X POST http://localhost:8000/orchestrate/stream \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-123" \
  -d '{
    "task": "Schedule a meeting and send invites",
    "tool_constraints": {
      "mode": "custom",
      "providers": ["google_calendar", "gmail"]
    }
  }'
```

**Tool Filtering**:
- Only tools from `google_calendar` and `gmail` providers will be available
- Other authorized providers (Slack, GitHub, etc.) will be filtered out
- Reduces LLM context size and improves focus

---

### Example 3: GUI Automation Task

**Request**:
```bash
curl -X POST http://localhost:8000/orchestrate/stream \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-123" \
  -d '{
    "task": "Open the calculator app and compute 123 * 456",
    "controller": {
      "host": "localhost",
      "port": 5900
    }
  }'
```

**Event Highlights**:
```
event: orchestrator.planning.completed
data: {"target":"computer_use","task_preview":"Open the calculator app and compute 123 * 456"}

event: computer_use.task.started
data: {"task":"Open calculator...","step_id":"step-cu-001"}

event: worker.step.started
data: {"step":1,"turn_count":0}

event: worker.step.completed
data: {"step":1,"plan":"Click application menu","action_type":"click"}

event: grounding.generate_coords.started
data: {"ref_expr":"calculator icon"}

event: grounding.generate_coords.completed
data: {"ref_expr":"calculator icon","coords":[120,340]}

event: computer_use.task.completed
data: {"success":true,"result":"Calculation result: 56088"}
```

---

### Example 4: Non-Streaming Request

**Request**:
```bash
curl -X POST http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-123" \
  -d '{
    "task": "Send a Slack message to #general channel saying \"Deployment complete\""
  }'
```

**Response** (single JSON, no streaming):
```json
{
  "task": "Send a Slack message to #general channel saying \"Deployment complete\"",
  "status": "success",
  "completion_reason": "ok",
  "steps": [
    {
      "step_id": "step-mcp-001",
      "target": "mcp",
      "task": "Send Slack message to #general",
      "result": "Message posted successfully to #general",
      "success": true,
      "error": null
    }
  ]
}
```

---

## Best Practices

### 1. Always Provide User ID
```javascript
// Good
fetch('/orchestrate/stream', {
  headers: { 'X-User-Id': currentUser.id }
})

// Bad (falls back to env var, may not be correct)
fetch('/orchestrate/stream')
```

### 2. Use Tool Constraints for Focused Tasks
```javascript
// For email-only task
{
  task: "Send status update email",
  tool_constraints: {
    mode: "custom",
    providers: ["gmail"]
  }
}
```

### 3. Handle All Error States
```javascript
// Listen for both failed and error events
eventSource.addEventListener('response.failed', handleError);
eventSource.addEventListener('error', handleError);

// Handle network errors
eventSource.onerror = handleNetworkError;
```

### 4. Show Progress for Long Tasks
```javascript
// Track step progress
const totalSteps = 10; // From orchestrator.task.started
const currentStep = 3;  // From orchestrator.step.dispatching

showProgressBar(currentStep / totalSteps);
```

### 5. Implement Keepalive Monitoring
```javascript
let lastKeepalive = Date.now();

eventSource.addEventListener('server.keepalive', (e) => {
  lastKeepalive = Date.now();
});

setInterval(() => {
  if (Date.now() - lastKeepalive > 30000) {
    // No keepalive for 30s, connection may be dead
    handleConnectionTimeout();
  }
}, 5000);
```

### 6. Group Events by Agent
```javascript
// Separate events for clearer UI
const orchestratorEvents = events.filter(e => e.event.startsWith('orchestrator.'));
const mcpEvents = events.filter(e => e.event.startsWith('mcp.'));
const computerUseEvents = events.filter(e =>
  e.event.startsWith('worker.') ||
  e.event.startsWith('code_agent.') ||
  e.event.startsWith('grounding.')
);
```

---

## Troubleshooting

### Issue: No Events Received
**Possible Causes**:
- Network proxy buffering SSE responses
- Missing `Cache-Control: no-cache` header handling
- Browser EventSource limitations

**Solutions**:
- Check proxy configuration (disable buffering for SSE)
- Use `fetch()` with streaming body instead of EventSource
- Verify server headers include `X-Accel-Buffering: no`

---

### Issue: Incomplete Events
**Cause**: EventSource buffer overflow or network interruption

**Solution**:
```javascript
// Implement reconnection logic
let lastEventId = null;

eventSource.addEventListener('orchestrator.step.completed', (e) => {
  lastEventId = e.data.step_id;
});

eventSource.onerror = () => {
  // Reconnect and resume from lastEventId
  reconnect(lastEventId);
};
```

---

### Issue: Tool Not Available
**Possible Causes**:
- Provider not OAuth-authorized for user
- Tool constraints filtering out the provider
- Provider temporarily unavailable

**Solutions**:
1. Check `mcp.toolbox.generated` event for available providers
2. Verify user has authorized the provider via OAuth flow
3. Remove tool constraints or add provider to allow list

---

### Issue: High Latency
**Possible Causes**:
- Large tool manifest (many authorized providers)
- Network latency to external APIs
- LLM inference time

**Solutions**:
1. Use `tool_constraints` in custom mode to reduce tool count
2. Monitor `server.keepalive` intervals to detect delays
3. Implement timeout handling (suggest user retry if > 2 minutes)

---

## Changelog

### Version 0.1.0 (Current)
- Initial orchestrator API release
- Multi-agent support (orchestrator, MCP, computer use)
- Tool constraints with auto/custom modes
- Comprehensive SSE event streaming
- Hierarchical logging infrastructure
- Multi-tenant user support

---

## Support

For issues, questions, or feature requests, please contact the TakeBridge team or file an issue in the project repository.
