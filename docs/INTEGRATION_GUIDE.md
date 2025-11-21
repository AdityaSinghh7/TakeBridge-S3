# MCP Agent Integration Guide

This guide covers integrating the MCP Agent with frontend applications, including OAuth flows, tool discovery, and task execution.

## Overview

The MCP Agent exposes HTTP APIs for:
- OAuth provider authentication (Gmail, Slack, etc.)
- Tool discovery and search
- Task execution with streaming results
- Connection management

**Base URL:** `http://localhost:8000` (development)

**Headers:**
- `X-User-Id`: User/tenant identifier (required for multi-tenancy)
- `Content-Type: application/json` (for POST requests)

---

## OAuth Integration

### Flow Overview

1. **Start OAuth** → Get authorization URL
2. **User Authorizes** → Composio handles OAuth
3. **Callback** → TakeBridge finalizes connection
4. **Poll Status** → Check authorization state
5. **Use Tools** → Execute tasks with authorized providers

### 1. List Available Providers

Get all providers with authorization status:

```http
GET /api/mcp/auth/providers
X-User-Id: dev-local
```

**Response:**
```json
{
  "providers": [
    {
      "provider": "gmail",
      "display_name": "Gmail",
      "authorized": true,
      "auth_config_present": true,
      "actions": ["gmail_send_email", "gmail_search"]
    },
    {
      "provider": "slack",
      "display_name": "Slack",
      "authorized": false,
      "auth_config_present": true,
      "actions": ["slack_post_message", "slack_search_messages"]
    }
  ]
}
```

### 2. Start OAuth Flow

```http
GET /api/mcp/auth/{provider}/start?redirect_success={url}&redirect_error={url}
X-User-Id: dev-local
```

**Parameters:**
- `redirect_success` (optional): URL to redirect after successful auth
- `redirect_error` (optional): URL to redirect on failure (gets `?error=...` appended)

**Response:**
```json
{
  "authorization_url": "https://backend.composio.dev/oauth?..."
}
```

**Frontend Implementation:**
```typescript
async function startOAuth(provider: string, userId: string) {
  const res = await fetch(
    `/api/mcp/auth/${provider}/start?` +
    `redirect_success=${encodeURIComponent(window.location.origin + '/integrations/callback')}&` +
    `redirect_error=${encodeURIComponent(window.location.origin + '/integrations/error')}`,
    { headers: { 'X-User-Id': userId } }
  );

  const { authorization_url } = await res.json();

  // Open in popup or redirect
  window.open(authorization_url, '_blank', 'width=600,height=700');
}
```

### 3. Poll Authorization Status

Use for real-time polling in UI:

```http
GET /api/mcp/auth/{provider}/status/live
X-User-Id: dev-local
```

**Response:**
```json
{
  "provider": "gmail",
  "authorized": true,
  "connected_account_id": "ca_123abc",
  "auth_config_id": "ac_456def",
  "mcp_url": "https://backend.composio.dev/api/v1/actions/GMAIL_*/execute",
  "has_auth_headers": true
}
```

**Frontend Polling:**
```typescript
async function pollAuthStatus(provider: string, userId: string) {
  const interval = setInterval(async () => {
    const res = await fetch(`/api/mcp/auth/${provider}/status/live`, {
      headers: { 'X-User-Id': userId }
    });
    const status = await res.json();

    if (status.authorized) {
      clearInterval(interval);
      onAuthSuccess(provider);
    }
  }, 2000); // Poll every 2 seconds

  // Stop after 60 seconds
  setTimeout(() => clearInterval(interval), 60000);
}
```

### 4. Disconnect Provider

```http
DELETE /api/mcp/auth/{provider}?connected_account_id={id}
X-User-Id: dev-local
```

**Response:**
```json
{
  "status": "disconnected",
  "provider": "gmail",
  "updated_accounts": 1,
  "cleared_connections": 1
}
```

---

## Tool Discovery

### List Available Tools

Get all tools across providers:

```http
GET /api/mcp/auth/tools/available?provider={slug}
X-User-Id: dev-local
```

**Parameters:**
- `provider` (optional): Filter by specific provider

**Response:**
```json
{
  "providers": [
    {
      "provider": "slack",
      "authorized": true,
      "actions": [
        {
          "name": "slack_post_message",
          "doc": "Post a message to Slack\n\nArgs:\n    channel: Channel ID or name\n    text: Message text"
        },
        {
          "name": "slack_search_messages",
          "doc": "Search Slack messages workspace-wide"
        }
      ]
    }
  ]
}
```

### Search Tools by Query

```http
GET /api/mcp/auth/tools/search?q={query}&detail={level}&limit={n}
X-User-Id: dev-local
```

**Parameters:**
- `q`: Search query (e.g., "gmail search")
- `detail`: `summary` or `full` (default: `summary`)
- `limit`: Max results (default: 10)

**Response (detail=full):**
```json
{
  "tools": [
    {
      "tool_id": "gmail.gmail_search",
      "provider": "gmail",
      "server": "gmail",
      "description": "Search Gmail messages",
      "signature": "gmail.gmail_search(query, max_results=20, include_payload=None)",
      "input_params": {
        "query": "str (required)",
        "max_results": "int (optional, default=20)",
        "include_payload": "bool | None (optional)"
      },
      "output_fields": [
        "messages[].messageId: string",
        "messages[].messageText: string",
        "messages[].sender: string",
        "messages[].subject: string",
        "resultSizeEstimate: integer"
      ],
      "score": 30.0
    }
  ]
}
```

---

## Task Execution

### Execute Task (Streaming)

Stream task execution with real-time updates:

```http
POST /orchestrate/stream
X-User-Id: dev-local
Content-Type: application/json
Accept: text/event-stream
```

**Request Body:**
```json
{
  "task": "Search my Gmail for emails from yesterday and send a summary to #general on Slack",
  "tool_constraints": {
    "mode": "auto",
    "providers": ["gmail", "slack"]
  }
}
```

**Tool Constraints:**
- `mode: "auto"` (default): Use all authorized providers
- `mode: "custom"`: Restrict to specified providers/tools
- `providers`: List of provider slugs
- `tools`: List of specific tool names

**Response Format:**

Server-Sent Events (SSE) with progressive updates:

```
event: response.created
data: {"status": "accepted"}

event: response.in_progress
data: {"status": "running"}

event: mcp.planner.started
data: {"task": "...", "user_id": "dev-local", "budget": {...}}

event: mcp.search.completed
data: {"query": "gmail search", "result_count": 2, "tool_ids": ["gmail.gmail_search", "gmail.gmail_send_email"]}

event: mcp.sandbox.run
data: {"success": true, "label": "email_summary", "code_preview": "from sandbox_py.servers import gmail..."}

event: response.completed
data: {"status": "success", "completion_reason": "DONE"}

event: response
data: {"success": true, "final_summary": "...", "user_id": "dev-local", ...}
```

**Frontend Implementation:**

```typescript
async function executeTask(task: string, userId: string) {
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

  return parseSSE(res.body);
}

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

**React Hook Example:**

```typescript
function useTaskExecution(userId: string) {
  const [status, setStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
  const [events, setEvents] = useState<any[]>([]);
  const [result, setResult] = useState<any>(null);

  const execute = async (task: string) => {
    setStatus('running');
    setEvents([]);

    try {
      for await (const event of await executeTask(task, userId)) {
        setEvents(prev => [...prev, event]);

        if (event.event === 'response.completed') {
          setStatus(event.data.status === 'success' ? 'success' : 'error');
        }

        if (event.event === 'response') {
          setResult(event.data);
        }
      }
    } catch (error) {
      setStatus('error');
      console.error('Task execution failed:', error);
    }
  };

  return { execute, status, events, result };
}
```

### Execute Task (Non-Streaming)

For fire-and-forget execution:

```http
POST /orchestrate
X-User-Id: dev-local
Content-Type: application/json
```

**Request:**
```json
{
  "task": "Send an email to john@example.com with the Q4 report"
}
```

**Response:**
```json
{
  "success": true,
  "final_summary": "Sent email to john@example.com with Q4 report attached",
  "user_id": "dev-local",
  "run_id": "abc123",
  "budget_usage": {
    "steps_taken": 3,
    "tool_calls": 1,
    "estimated_llm_cost_usd": 0.0023
  },
  "steps": [...]
}
```

---

## Key Events Reference

### Lifecycle Events

| Event | Description | Payload |
|-------|-------------|---------|
| `response.created` | Task accepted | `{"status": "accepted"}` |
| `response.in_progress` | Execution started | `{"status": "running"}` |
| `response.completed` | Task completed | `{"status": "success", "completion_reason": "DONE"}` |
| `response.failed` | Task failed | `{"error": "..."}` |
| `response` | Final result | Full `MCPTaskResult` |

### Planning Events

| Event | Description | Payload |
|-------|-------------|---------|
| `mcp.planner.started` | Planner initialized | `{"task": "...", "budget": {...}}` |
| `mcp.search.completed` | Tool search finished | `{"query": "...", "tool_ids": [...]}` |
| `mcp.llm.completed` | LLM generated command | `{"model": "o4-mini", "output_chars": 123}` |

### Execution Events

| Event | Description | Payload |
|-------|-------------|---------|
| `mcp.sandbox.run` | Sandbox code executed | `{"success": true, "label": "...", "code_preview": "..."}` |
| `mcp.tool.call` | MCP tool called | `{"provider": "gmail", "tool": "GMAIL_SEARCH"}` |

---

## Error Handling

### HTTP Errors

All errors return JSON with `detail` field:

```json
{
  "detail": "Provider gmail is not authorized for user dev-local"
}
```

**Common Status Codes:**
- `400`: Bad request (invalid parameters)
- `401`: Unauthorized (invalid X-User-Id)
- `404`: Resource not found (provider doesn't exist)
- `500`: Internal server error

### Task Execution Errors

Failed tasks return `success: false` in final result:

```json
{
  "success": false,
  "final_summary": "Task failed: budget exhausted",
  "error": "budget_exhausted",
  "error_code": "budget_exhausted",
  "error_message": "Maximum steps exceeded (10/10)",
  "budget_usage": {...}
}
```

**Error Codes:**
- `budget_exhausted`: Exceeded max steps/cost
- `unauthorized`: Provider not connected
- `protocol_error`: Invalid LLM command format
- `planner_llm_disabled`: LLM not enabled

---

## Best Practices

### 1. Handle OAuth Popups

```typescript
// Open OAuth in popup, poll for success
function handleOAuth(provider: string) {
  startOAuth(provider, userId);

  // Start polling in background
  pollAuthStatus(provider, userId);

  // Show loading state in UI
  showOAuthPending(provider);
}
```

### 2. Stream UI Updates

```typescript
// Update UI progressively as events arrive
for await (const event of await executeTask(task, userId)) {
  switch (event.event) {
    case 'mcp.search.completed':
      showToolsFound(event.data.tool_ids);
      break;
    case 'mcp.sandbox.run':
      showCodeExecution(event.data.code_preview);
      break;
    case 'response.completed':
      showFinalResult();
      break;
  }
}
```

### 3. Handle Connection Errors

```typescript
try {
  const stream = await executeTask(task, userId);
  for await (const event of stream) {
    // Process events
  }
} catch (error) {
  if (error.message.includes('unauthorized')) {
    // Prompt user to connect provider
    showOAuthPrompt();
  } else {
    // Show generic error
    showError(error.message);
  }
}
```

### 4. Cache Provider Status

```typescript
// Cache auth status to avoid repeated API calls
const authCache = new Map<string, boolean>();

async function isProviderAuthorized(provider: string, userId: string) {
  if (authCache.has(provider)) {
    return authCache.get(provider);
  }

  const res = await fetch(`/api/mcp/auth/${provider}/status/live`, {
    headers: { 'X-User-Id': userId }
  });
  const { authorized } = await res.json();

  authCache.set(provider, authorized);
  return authorized;
}

// Clear cache after OAuth completion
authCache.delete(provider);
```

---

## Testing

### Manual Testing with cURL

```bash
# 1. List providers
curl -H "X-User-Id: dev-local" \
  http://localhost:8000/api/mcp/auth/providers

# 2. Search tools
curl -H "X-User-Id: dev-local" \
  "http://localhost:8000/api/mcp/auth/tools/search?q=gmail&detail=full"

# 3. Execute task (streaming)
curl -N -H "X-User-Id: dev-local" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"task":"Search my emails"}' \
  http://localhost:8000/orchestrate/stream
```

### Python Testing

```python
from mcp_agent.agent import execute_mcp_task, Budget

result = execute_mcp_task(
    task="Find my most recent email and summarize it",
    user_id="dev-local",
    budget=Budget(max_steps=10, max_tool_calls=5),
)

print(f"Success: {result['success']}")
print(f"Summary: {result['final_summary']}")
```

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [DEVELOPMENT.md](./DEVELOPMENT.md) - Adding new tools and providers
- [../README.md](../README.md) - Repository overview
