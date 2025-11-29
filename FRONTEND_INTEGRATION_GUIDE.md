# Frontend Integration Guide - Auth & Workspace Management

## Overview

The TakeBridge API has been updated with **Supabase JWT authentication** and **automatic workspace management**. All endpoints now require authentication, and workspace/VM management is handled automatically.

## Key Changes

### Before (Old Flow)
```
Frontend → /app/run_task (with user_id) 
         → Server gets workspace
         → Server calls /orchestrate/stream via HTTP
```

### After (New Flow)
```
Frontend → /orchestrate/stream (with JWT token)
         → Server auto-gets/creates workspace
         → Server runs orchestrator directly
```

## Authentication

### How It Works

1. **User logs in via Supabase** (handled by your frontend)
2. **Frontend receives JWT token** from Supabase
3. **All API requests include JWT token** in `Authorization` header
4. **Server validates token** and extracts `user_id` automatically

### Required Header

All authenticated endpoints require:
```
Authorization: Bearer <supabase-jwt-token>
```

The `user_id` is automatically extracted from the token's `sub` claim - **you no longer need to pass `X-User-Id` header**.

## API Endpoints

### Public Endpoints (No Auth Required)

#### `GET /health`
Health check endpoint.

```javascript
const response = await fetch('https://api.takebridge.com/health');
const data = await response.json();
// { status: "ok" }
```

#### `GET /debug/auth`
Check auth configuration (for debugging).

```javascript
const response = await fetch('https://api.takebridge.com/debug/auth');
const data = await response.json();
// { jwt_secret_configured: true, jwt_secret_length: 88, ... }
```

### Authenticated Endpoints (Require JWT Token)

#### `POST /orchestrate/stream` ⭐ **PRIMARY ENDPOINT**

**Run a task with streaming response (SSE).**

This is now the **main endpoint** you should use. It automatically:
- Gets/creates workspace for the user
- Uses workspace's VM controller
- Streams results via Server-Sent Events

**Request:**
```javascript
const response = await fetch('https://api.takebridge.com/orchestrate/stream', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${supabaseToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    task: "Open Chrome and search for Python",
    // Optional: tool constraints
    tool_constraints: {
      mode: "auto",  // or "custom"
      providers: ["gmail", "slack"],  // if mode is "custom"
      tools: ["gmail_send_email"]     // if mode is "custom"
    }
    // controller.base_url is auto-resolved from workspace
    // You can override it if needed:
    // controller: { base_url: "http://custom-vm:5000" }
  })
});

// Handle Server-Sent Events
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const chunk = decoder.decode(value);
  const lines = chunk.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('event: ')) {
      const event = line.substring(7);
    } else if (line.startsWith('data: ')) {
      const data = JSON.parse(line.substring(6));
      
      if (event === 'response.created') {
        console.log('Task accepted:', data);
      } else if (event === 'response.in_progress') {
        console.log('Task running...');
      } else if (event === 'response') {
        console.log('Task result:', data);
        // data contains: { task, status, completion_reason, steps }
      } else if (event === 'response.completed') {
        console.log('Task completed:', data);
      } else if (event === 'response.failed') {
        console.error('Task failed:', data);
      }
    }
  }
}
```

**Alternative: Using EventSource (simpler for GET requests)**

```javascript
// For simple GET requests
const eventSource = new EventSource(
  `https://api.takebridge.com/orchestrate/stream?task=${encodeURIComponent('Open Chrome')}`,
  {
    headers: {
      'Authorization': `Bearer ${supabaseToken}`
    }
  }
);

eventSource.addEventListener('response', (e) => {
  const data = JSON.parse(e.data);
  console.log('Task result:', data);
});

eventSource.addEventListener('response.completed', (e) => {
  const data = JSON.parse(e.data);
  console.log('Task completed:', data);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  console.error('SSE error:', e);
  eventSource.close();
});
```

#### `POST /orchestrate` (Non-Streaming)

**Run a task and wait for complete result.**

```javascript
const response = await fetch('https://api.takebridge.com/orchestrate', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${supabaseToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    task: "Open Chrome and search for Python",
    tool_constraints: {
      mode: "auto"
    }
  })
});

const result = await response.json();
// {
//   task: "Open Chrome and search for Python",
//   status: "success" | "partial",
//   completion_reason: "ok",
//   steps: [...]
// }
```

#### `GET /orchestrate/stream` (Simple GET)

**Streaming endpoint with task as query parameter.**

```javascript
const eventSource = new EventSource(
  `https://api.takebridge.com/orchestrate/stream?task=${encodeURIComponent('Open Chrome')}`,
  {
    headers: {
      'Authorization': `Bearer ${supabaseToken}`
    }
  }
);
// Handle events same as POST /orchestrate/stream
```

#### `GET /app/workspace`

**Get user's current workspace information.**

```javascript
const response = await fetch('https://api.takebridge.com/app/workspace', {
  headers: {
    'Authorization': `Bearer ${supabaseToken}`
  }
});

const workspace = await response.json();
// {
//   id: "workspace-uuid",
//   user_id: "user-uuid",
//   status: "running" | "terminated",
//   controller_base_url: "http://x.x.x.x:5000",
//   vnc_url: "ws://x.x.x.x:6080",
//   vm_instance_id: "i-xxxxx",
//   cloud_region: "us-west-2",
//   created_at: "2025-01-01T00:00:00Z",
//   last_used_at: "2025-01-01T00:00:00Z"
// }
```

**Note:** Returns 404 if no workspace exists yet. Workspace is created automatically on first `/orchestrate` request.

#### `POST /app/workspace/terminate`

**Terminate user's active workspace (stops VM).**

```javascript
const response = await fetch('https://api.takebridge.com/app/workspace/terminate', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${supabaseToken}`
  }
});

const result = await response.json();
// If workspace was terminated:
// { id: "...", status: "terminated", ... }
// If no active workspace:
// { status: "no_active_workspace" }
```

#### `GET /config`

**Get default orchestrator configuration.**

```javascript
const response = await fetch('https://api.takebridge.com/config', {
  headers: {
    'Authorization': `Bearer ${supabaseToken}`
  }
});

const config = await response.json();
// {
//   controller: { ... },
//   worker: { ... },
//   grounding: { ... }
// }
```

## Migration Guide

### Old Code (Before)
```javascript
// ❌ OLD: Using /app/run_task with X-User-Id header
const response = await fetch('https://api.takebridge.com/app/run_task', {
  method: 'POST',
  headers: {
    'X-User-Id': userId,  // ❌ No longer needed
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    task: "Open Chrome"
  })
});
```

### New Code (After)
```javascript
// ✅ NEW: Using /orchestrate/stream with JWT token
const response = await fetch('https://api.takebridge.com/orchestrate/stream', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${supabaseToken}`,  // ✅ JWT token
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    task: "Open Chrome"
  })
});
```

## Complete Example: React Component

```javascript
import { useState, useEffect } from 'react';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

function TaskRunner() {
  const [token, setToken] = useState(null);
  const [task, setTask] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  // Get JWT token on mount
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
      }
    });

    // Listen for auth changes
    supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        setToken(session.access_token);
      } else {
        setToken(null);
      }
    });
  }, []);

  const runTask = async () => {
    if (!token) {
      alert('Please log in first');
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch('https://api.takebridge.com/orchestrate/stream', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          task: task,
          tool_constraints: {
            mode: 'auto'
          }
        })
      });

      // Handle SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        let currentEvent = null;
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.substring(7).trim();
          } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.substring(6));
            
            if (currentEvent === 'response') {
              setResult(data);
            } else if (currentEvent === 'response.completed') {
              setLoading(false);
            } else if (currentEvent === 'response.failed') {
              setLoading(false);
              alert(`Task failed: ${data.error}`);
            }
          }
        }
      }
    } catch (error) {
      console.error('Error:', error);
      setLoading(false);
      alert('Failed to run task');
    }
  };

  return (
    <div>
      <input
        value={task}
        onChange={(e) => setTask(e.target.value)}
        placeholder="Enter task..."
      />
      <button onClick={runTask} disabled={!token || loading}>
        {loading ? 'Running...' : 'Run Task'}
      </button>
      
      {result && (
        <div>
          <h3>Result:</h3>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
```

## Error Handling

### Authentication Errors

```javascript
// 401 Unauthorized - Missing or invalid token
if (response.status === 401) {
  const error = await response.json();
  // { detail: "Not authenticated - missing Authorization header" }
  // or
  // { detail: "Invalid token: ..." }
  // or
  // { detail: "Token has expired" }
  
  // Redirect to login or refresh token
  supabase.auth.refreshSession();
}
```

### Workspace Errors

```javascript
// 404 Not Found - No workspace exists yet
if (response.status === 404) {
  // This is normal for new users
  // Workspace will be created automatically on first /orchestrate request
}
```

### Network Errors

```javascript
try {
  const response = await fetch(...);
  if (!response.ok) {
    const error = await response.json();
    console.error('API Error:', error);
  }
} catch (error) {
  // Network error, timeout, etc.
  console.error('Network Error:', error);
}
```

## Best Practices

### 1. Token Management

- **Store token securely** (don't put in localStorage if possible)
- **Refresh token** before it expires
- **Handle token expiration** gracefully

```javascript
// Check if token is expired
const session = await supabase.auth.getSession();
if (session.data.session) {
  const expiresAt = session.data.session.expires_at;
  const now = Math.floor(Date.now() / 1000);
  
  if (expiresAt - now < 300) { // Less than 5 minutes
    await supabase.auth.refreshSession();
  }
}
```

### 2. Workspace Management

- **Don't create workspace manually** - it's automatic
- **Check workspace status** before showing VM controls
- **Handle workspace creation delays** (VM spin-up takes time)

```javascript
// Check workspace status
const checkWorkspace = async () => {
  const response = await fetch('https://api.takebridge.com/app/workspace', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  if (response.status === 404) {
    // No workspace yet - will be created on first task
    return null;
  }
  
  return await response.json();
};
```

### 3. Streaming Responses

- **Handle all event types** (not just 'response')
- **Show progress indicators** for 'response.in_progress'
- **Handle keepalive events** to detect connection issues
- **Clean up EventSource** when component unmounts

```javascript
useEffect(() => {
  const eventSource = new EventSource(...);
  
  return () => {
    eventSource.close(); // Cleanup on unmount
  };
}, []);
```

## Summary of Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Authentication** | `X-User-Id` header | JWT token in `Authorization` header |
| **Primary Endpoint** | `/app/run_task` | `/orchestrate/stream` |
| **Workspace Management** | Manual via `/app/run_task` | Automatic on first request |
| **User ID** | Passed in header | Extracted from JWT token |
| **VM Controller** | Passed in request | Auto-resolved from workspace |

## Quick Reference

```javascript
// ✅ Always include JWT token
headers: {
  'Authorization': `Bearer ${supabaseToken}`
}

// ✅ Use /orchestrate/stream for tasks
POST /orchestrate/stream
{
  task: "your task",
  tool_constraints: { mode: "auto" }
}

// ✅ Workspace is automatic
// No need to call /app/run_task anymore
// Workspace created on first /orchestrate request
```

## Support

For issues or questions:
- Check `/debug/auth` endpoint for auth config
- Check `/health` endpoint for server status
- Review error responses for detailed messages
- Check server logs for backend issues

