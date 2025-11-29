# Changes Summary - Auth & Workspace Management

## TL;DR

- ✅ **All endpoints now require JWT authentication** (Supabase tokens)
- ✅ **Use `/orchestrate/stream` directly** - no need for `/app/run_task`
- ✅ **Workspace management is automatic** - created on first request
- ✅ **User ID extracted from JWT token** - no more `X-User-Id` header

## What Changed

### Authentication
- **Before:** Optional `X-User-Id` header
- **After:** Required `Authorization: Bearer <jwt-token>` header
- **Impact:** All endpoints now require valid Supabase JWT token

### Primary Endpoint
- **Before:** `/app/run_task` → calls orchestrator via HTTP
- **After:** `/orchestrate/stream` → runs orchestrator directly
- **Impact:** Simpler flow, one less HTTP hop

### Workspace Management
- **Before:** Manual workspace creation/retrieval
- **After:** Automatic - workspace created on first `/orchestrate` request
- **Impact:** Frontend doesn't need to manage workspace lifecycle

### User Identification
- **Before:** Pass `user_id` in `X-User-Id` header
- **After:** `user_id` extracted from JWT token (`sub` claim)
- **Impact:** No need to pass user ID explicitly

## Frontend Migration Checklist

- [ ] Replace `X-User-Id` header with `Authorization: Bearer <token>`
- [ ] Update endpoint from `/app/run_task` to `/orchestrate/stream`
- [ ] Remove workspace creation/retrieval logic (now automatic)
- [ ] Update error handling for 401 (authentication errors)
- [ ] Test with Supabase JWT tokens

## Quick Code Change

### Before
```javascript
fetch('/app/run_task', {
  headers: { 'X-User-Id': userId },
  body: JSON.stringify({ task: '...' })
})
```

### After
```javascript
fetch('/orchestrate/stream', {
  headers: { 'Authorization': `Bearer ${jwtToken}` },
  body: JSON.stringify({ task: '...' })
})
```

## New Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/orchestrate/stream` | POST | ✅ | **Main endpoint** - Run task with streaming |
| `/orchestrate/stream` | GET | ✅ | Run task (simple query param) |
| `/orchestrate` | POST | ✅ | Run task (non-streaming) |
| `/app/workspace` | GET | ✅ | Get workspace info |
| `/app/workspace/terminate` | POST | ✅ | Terminate workspace |
| `/config` | GET | ✅ | Get default config |
| `/health` | GET | ❌ | Health check |
| `/debug/auth` | GET | ❌ | Debug auth config |

## Breaking Changes

1. **All endpoints require authentication** (except `/health` and `/debug/auth`)
2. **`X-User-Id` header no longer used** - user ID from JWT token
3. **`/app/run_task` deprecated** - use `/orchestrate/stream` instead

## Benefits

- ✅ **Simpler frontend code** - no workspace management needed
- ✅ **Better security** - JWT-based authentication
- ✅ **Automatic multi-tenancy** - user isolation via JWT
- ✅ **Faster requests** - one less HTTP hop
- ✅ **Consistent auth** - same token across all endpoints

## Documentation

- **Full Guide:** See `FRONTEND_INTEGRATION_GUIDE.md`
- **Testing:** See `TESTING_GUIDE.md` and `QUICK_TEST.md`
- **API Reference:** See `docs/API_REFERENCE.md`

