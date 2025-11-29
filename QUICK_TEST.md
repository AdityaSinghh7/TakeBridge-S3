# Quick Testing Reference

## 1. Generate a Test Token

```bash
# Make sure SUPABASE_JWT_SECRET is in your .env file
python scripts/generate_test_token.py test-user-123 test@example.com

# Or use default values
python scripts/generate_test_token.py
```

Copy the token from the output.

## 2. Set Token as Environment Variable

```bash
export JWT_TOKEN="paste-your-token-here"
```

## 3. Quick Test Commands

### Health Check
```bash
curl http://localhost:8000/health
```

### Check Auth Config
```bash
curl http://localhost:8000/debug/auth
```

### Get Workspace (creates if doesn't exist on first request)
```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:8000/app/workspace
```

### Run Task (Streaming)
```bash
curl -X POST \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task": "Open Chrome"}' \
  http://localhost:8000/orchestrate/stream
```

### Run Task (Non-Streaming)
```bash
curl -X POST \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task": "Open Chrome"}' \
  http://localhost:8000/orchestrate
```

### Get Config
```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:8000/config
```

### Terminate Workspace
```bash
curl -X POST \
  -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:8000/app/workspace/terminate
```

## Complete Test Script

Save this as `test_api.sh`:

```bash
#!/bin/bash

# Set your token
export JWT_TOKEN="your-token-here"

echo "1. Health check..."
curl -s http://localhost:8000/health | jq

echo -e "\n2. Auth config..."
curl -s http://localhost:8000/debug/auth | jq

echo -e "\n3. Get workspace..."
curl -s -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:8000/app/workspace | jq

echo -e "\n4. Run task (non-streaming)..."
curl -s -X POST \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task": "Open Chrome"}' \
  http://localhost:8000/orchestrate | jq

echo -e "\n5. Get workspace again..."
curl -s -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:8000/app/workspace | jq
```

Make it executable and run:
```bash
chmod +x test_api.sh
./test_api.sh
```

## Testing Without VM (Mock Mode)

If you don't have AWS configured, the workspace creation will fail. You can test the auth and API structure by:

1. **Skip workspace creation** - Just test auth:
   ```bash
   curl -H "Authorization: Bearer $JWT_TOKEN" \
     http://localhost:8000/config
   ```

2. **Test with manual controller URL** - Provide controller in payload:
   ```bash
   curl -X POST \
     -H "Authorization: Bearer $JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "task": "Open Chrome",
       "controller": {
         "base_url": "http://localhost:5000"
       }
     }' \
     http://localhost:8000/orchestrate/stream
   ```

## Common Issues

### "Not authenticated"
- Token is missing or invalid
- Check: `echo $JWT_TOKEN`
- Regenerate token: `python scripts/generate_test_token.py`

### "JWT secret not configured"
- Add to `.env`: `SUPABASE_JWT_SECRET=your-secret`
- Or export: `export SUPABASE_JWT_SECRET=your-secret`

### "No workspace found"
- Normal for new users
- Workspace is created on first `/orchestrate` request
- If AWS not configured, workspace creation will fail

### Connection refused on controller
- VM not started or controller not running
- Check VM status in AWS console
- Or use a local controller for testing

