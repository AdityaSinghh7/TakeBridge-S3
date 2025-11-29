# Frontend Connection Fix

## Problem

Your frontend is trying to connect to `http://127.0.0.1:8000` but the server is running on `https://localhost:8000` (HTTPS with SSL).

## Solutions

### Option 1: Use HTTPS in Frontend (Recommended)

Change your frontend URL from:
```javascript
// ❌ Wrong
const url = "http://127.0.0.1:8000/orchestrate/stream";
```

To:
```javascript
// ✅ Correct
const url = "https://localhost:8000/orchestrate/stream";
```

**Note:** When using HTTPS with self-signed certificates in development, you may need to:
- Accept the certificate in your browser first
- Or configure your HTTP client to ignore certificate errors (for dev only)

### Option 2: Run Server on HTTP (For Local Development)

If you want to use HTTP instead, you can run the server without SSL:

```bash
# Stop the current server (Ctrl+C)

# Run without SSL
uvicorn server.api.server:app --host 0.0.0.0 --port 8000
```

Then your frontend can use:
```javascript
const url = "http://127.0.0.1:8000/orchestrate/stream";
```

### Option 3: Handle Self-Signed Certificates (Node.js/Electron)

If you're using Node.js/Electron and need to accept self-signed certificates:

```javascript
// For Node.js fetch/axios
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'; // ⚠️ Dev only!

// Or for Electron
const { app } = require('electron');
app.commandLine.appendSwitch('ignore-certificate-errors');
```

## Additional Issues to Check

### 1. CORS Configuration

The server allows all origins (`"*"`), so CORS should be fine. But if you still get CORS errors:

```javascript
// Make sure you're including credentials if needed
fetch(url, {
  credentials: 'include', // or 'same-origin'
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
})
```

### 2. Streaming Response Handling

The `/orchestrate/stream` endpoint returns Server-Sent Events (SSE). Make sure you're handling it correctly:

```javascript
// ✅ Correct: Handle as stream
const response = await fetch('https://localhost:8000/orchestrate/stream', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    task: "open chrome",
    tool_constraints: { mode: "auto" }
  })
});

// Read as stream
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop() || '';
  
  let currentEvent = null;
  for (const line of lines) {
    if (line.startsWith('event: ')) {
      currentEvent = line.substring(7).trim();
    } else if (line.startsWith('data: ')) {
      const data = JSON.parse(line.substring(6));
      console.log(`Event: ${currentEvent}`, data);
    }
  }
}
```

### 3. Electron-Specific Issues

If you're using Electron, you might need to:

```javascript
// In your Electron main process
const { app, BrowserWindow } = require('electron');

// Allow insecure certificates (dev only)
app.commandLine.appendSwitch('ignore-certificate-errors');

// Or configure session
app.on('ready', () => {
  const ses = session.defaultSession;
  ses.setCertificateVerifyProc((request, callback) => {
    // For localhost, always accept
    if (request.hostname === 'localhost' || request.hostname === '127.0.0.1') {
      callback(0); // Accept
    } else {
      callback(-2); // Use default verification
    }
  });
});
```

## Quick Fix for Your Code

Based on your error, update your frontend code:

```javascript
// Change from:
const url = "http://127.0.0.1:8000/orchestrate/stream";

// To:
const url = "https://localhost:8000/orchestrate/stream";

// And make sure you're handling the streaming response correctly
const response = await fetch(url, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwtToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    task: "open chrome",
    tool_constraints: { mode: "auto" }
  })
});

// Handle as stream (not JSON)
const reader = response.body.getReader();
// ... rest of streaming code
```

## Testing

Test the connection first:

```bash
# Test HTTPS endpoint
curl -k https://localhost:8000/health

# Test with token
curl -k -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task":"test"}' \
  https://localhost:8000/orchestrate/stream
```

If curl works but your frontend doesn't, it's likely:
1. Certificate validation issue (use `-k` flag equivalent in your code)
2. Streaming response not handled correctly
3. CORS issue (though server allows all origins)

