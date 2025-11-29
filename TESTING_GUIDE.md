# Testing Guide - Auth & Workspace Endpoints

## Prerequisites

1. **Get a Supabase JWT Token**

   You need a valid JWT token from Supabase. There are a few ways:

   **Option A: Use Supabase Dashboard (Easiest)**
   - Go to your Supabase project → Authentication → Users
   - Create a test user or use an existing one
   - Copy the JWT token from the user's session (or use Supabase client SDK)

   **Option B: Use Supabase Client (Recommended for testing)**
   ```bash
   # Install Supabase JS client (if using Node.js)
   npm install @supabase/supabase-js
   
   # Or use Python client
   pip install supabase
   ```

   **Option C: Generate a test token manually (for development only)**
   ```python
   # test_token_generator.py
   from jose import jwt
   import time
   
   SECRET = "your-supabase-jwt-secret"
   user_id = "test-user-123"
   
   token = jwt.encode({
       "sub": user_id,
       "email": "test@example.com",
       "aud": "authenticated",
       "role": "authenticated",
       "iat": int(time.time()),
       "exp": int(time.time()) + 3600  # 1 hour
   }, SECRET, algorithm="HS256")
   
   print(token)
   ```

2. **Set Environment Variables**
   ```bash
   export SUPABASE_JWT_SECRET="your-supabase-jwt-secret"
   export DB_URL="postgresql://..."
   # Optional AWS config if testing VM creation
   export AWS_REGION="us-west-2"
   export AGENT_AMI_ID="ami-xxx"
   ```

3. **Start the Server**
   ```bash
   uvicorn server.api.server:app --host 0.0.0.0 --port 8000
   ```

## Testing Endpoints

### 1. Health Check (No Auth Required)

```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{"status": "ok"}
```

### 2. Debug Auth Config (No Auth Required)

```bash
curl http://localhost:8000/debug/auth
```

**Expected Response:**
```json
{
  "jwt_secret_configured": true,
  "jwt_secret_length": 64,
  "jwt_algorithm": "HS256"
}
```

### 3. Get Workspace Info (Requires Auth)

```bash
# Replace YOUR_JWT_TOKEN with actual token
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/app/workspace
```

**Expected Response (if workspace exists):**
```json
{
  "id": "workspace-uuid",
  "user_id": "user-uuid-from-supabase",
  "status": "running",
  "controller_base_url": "http://x.x.x.x:5000",
  "vnc_url": "ws://x.x.x.x:6080",
  "vm_instance_id": "i-xxxxx",
  "cloud_region": "us-west-2",
  "created_at": "2025-01-01T00:00:00Z",
  "last_used_at": "2025-01-01T00:00:00Z"
}
```

**Expected Response (if no workspace exists):**
```json
{
  "detail": "No workspace found for this user"
}
```
Status: 404

### 4. Run Task via /orchestrate/stream (Requires Auth)

**POST with full payload:**
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Open Chrome browser",
    "tool_constraints": {
      "mode": "auto"
    }
  }' \
  http://localhost:8000/orchestrate/stream
```

**GET with query param:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/orchestrate/stream?task=Open%20Chrome"
```

**Expected Response:**
Server-Sent Events (SSE) stream:
```
event: response.created
data: {"status":"accepted"}

event: response.in_progress
data: {"status":"running"}

event: server.keepalive
data: {"ts":1234567890}

event: response
data: {"task":"Open Chrome browser","status":"success",...}

event: response.completed
data: {"status":"success","completion_reason":"ok"}
```

### 5. Run Task (Non-Streaming) via /orchestrate

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Open Chrome browser"
  }' \
  http://localhost:8000/orchestrate
```

**Expected Response:**
```json
{
  "task": "Open Chrome browser",
  "status": "success",
  "completion_reason": "ok",
  "steps": [...]
}
```

### 6. Get Config (Requires Auth)

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/config
```

**Expected Response:**
```json
{
  "controller": {...},
  "worker": {...},
  "grounding": {...}
}
```

### 7. Terminate Workspace (Requires Auth)

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/app/workspace/terminate
```

**Expected Response (if workspace was terminated):**
```json
{
  "id": "workspace-uuid",
  "status": "terminated",
  ...
}
```

**Expected Response (if no active workspace):**
```json
{
  "status": "no_active_workspace"
}
```

## Error Responses

### Missing Authorization Header
```bash
curl http://localhost:8000/orchestrate/stream?task=test
```

**Response:**
```json
{
  "detail": "Not authenticated - missing Authorization header"
}
```
Status: 401

### Invalid Token
```bash
curl -H "Authorization: Bearer invalid-token" \
  http://localhost:8000/orchestrate/stream?task=test
```

**Response:**
```json
{
  "detail": "Invalid token: ..."
}
```
Status: 401

### Expired Token
```json
{
  "detail": "Token has expired"
}
```
Status: 401

## Testing Workflow

### Complete Test Flow

1. **Check server is running:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Verify auth config:**
   ```bash
   curl http://localhost:8000/debug/auth
   ```

3. **Get workspace (will create one if it doesn't exist):**
   ```bash
   curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/app/workspace
   ```

4. **Run a simple task:**
   ```bash
   curl -X POST \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"task": "Open Chrome"}' \
     http://localhost:8000/orchestrate/stream
   ```

5. **Check workspace again (should show updated last_used_at):**
   ```bash
   curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/app/workspace
   ```

## Using Environment Variables

Save your token in an environment variable for easier testing:

```bash
export JWT_TOKEN="your-jwt-token-here"

# Then use it in curl:
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:8000/app/workspace
```

## Testing with Different Users

To test multi-tenancy, use different JWT tokens (different `sub` claims):

```bash
# User 1
export JWT_TOKEN_USER1="token-for-user-1"
curl -H "Authorization: Bearer $JWT_TOKEN_USER1" \
  http://localhost:8000/app/workspace

# User 2
export JWT_TOKEN_USER2="token-for-user-2"
curl -H "Authorization: Bearer $JWT_TOKEN_USER2" \
  http://localhost:8000/app/workspace
```

Each user should get their own workspace.

## Troubleshooting

### "JWT secret not configured"
- Check `SUPABASE_JWT_SECRET` is set in environment
- Verify it matches your Supabase project's JWT secret

### "No workspace found"
- This is normal for new users
- Workspace is created automatically on first `/orchestrate` request

### "Timeout waiting for EC2 instance"
- AWS credentials not configured
- Or AWS config (AMI, security groups, etc.) is incorrect
- Check AWS credentials: `aws sts get-caller-identity`

### "Connection refused" on controller_base_url
- VM might not be fully started yet
- Or controller service isn't running on the VM
- Check VM health: `curl http://VM_IP:5000/health`

