# MCP Auth Integration with JWT Authentication

## Overview

The MCP (Model Context Protocol) auth routes have been updated to support **both JWT authentication and legacy X-User-Id headers**. This provides backward compatibility while enabling secure JWT-based authentication.

## How It Works

### Dual Authentication Support

The MCP auth endpoints support **two authentication methods**:

1. **JWT Authentication (Preferred)**
   - Uses Supabase JWT token in `Authorization: Bearer <token>` header
   - Extracts `user_id` from token's `sub` claim
   - More secure and consistent with other endpoints

2. **Legacy X-User-Id (Fallback)**
   - Uses `X-User-Id` header or `user_id` query parameter
   - Required for OAuth callbacks from external providers (Composio, etc.)
   - These callbacks can't include JWT tokens

### Authentication Flow

```python
def _get_user_id_from_jwt_or_header(request, current_user):
    # 1. Try JWT auth first (if token provided)
    if current_user:
        return current_user.sub
    
    # 2. Fallback to X-User-Id header
    # 3. Fallback to user_id query parameter
    # 4. Fallback to TB_DEFAULT_USER_ID env var
```

## Endpoint Behavior

### Standard Endpoints (JWT Preferred)

These endpoints prefer JWT but accept legacy auth:

- `GET /api/mcp/auth/providers` - List providers
- `GET /api/mcp/auth/tools/available` - List available tools
- `GET /api/mcp/auth/tools/search` - Search tools
- `GET /api/mcp/auth/{provider}/start` - Start OAuth flow
- `POST /api/mcp/auth/{provider}/refresh` - Refresh OAuth token
- `GET /api/mcp/auth/{provider}/status/live` - Get provider status
- `POST /api/mcp/auth/{provider}/finalize` - Finalize connection
- `DELETE /api/mcp/auth/{provider}` - Disconnect provider

**Example with JWT:**
```javascript
// Preferred: Use JWT token
fetch('/api/mcp/auth/providers', {
  headers: {
    'Authorization': `Bearer ${supabaseToken}`
  }
})
```

**Example with Legacy:**
```javascript
// Fallback: Use X-User-Id header
fetch('/api/mcp/auth/providers', {
  headers: {
    'X-User-Id': userId
  }
})
```

### OAuth Callback Endpoint (Special Case)

`GET /api/mcp/auth/{provider}/callback` is **special** because:

1. **Called by external OAuth providers** (Composio, Google, etc.)
2. **Cannot include JWT tokens** - external services don't have your JWT secret
3. **Uses `user_id` in query parameters** - embedded in redirect URL

**How it works:**
```
User clicks "Connect Gmail"
  ↓
Frontend calls: GET /api/mcp/auth/gmail/start
  (with JWT token)
  ↓
Server creates OAuth URL with user_id in query: 
  https://composio.dev/oauth?user_id=xxx&redirect_uri=...
  ↓
User authorizes on Composio
  ↓
Composio redirects to: /api/mcp/auth/gmail/callback?user_id=xxx&code=...
  (NO JWT token - uses user_id from query)
  ↓
Server finalizes connection using user_id from query
```

## Integration with Workspace Management

### User Identity Consistency

Both authentication methods extract the same `user_id`:
- **JWT**: `user_id` = token's `sub` claim (Supabase user UUID)
- **Legacy**: `user_id` = normalized value from header/query

This ensures:
- ✅ Same user gets same workspace
- ✅ Same user gets same MCP connections
- ✅ Consistent multi-tenancy

### Workspace + MCP Connection Flow

```
1. User logs in → Gets JWT token (user_id = "abc-123")
   ↓
2. User connects Gmail → MCP auth creates connection (user_id = "abc-123")
   ↓
3. User runs task → Workspace created (user_id = "abc-123")
   ↓
4. Task uses Gmail tools → MCP connection found (user_id = "abc-123")
```

All using the same `user_id` from JWT token!

## Frontend Integration

### Recommended Approach

**Use JWT tokens for all MCP auth endpoints:**

```javascript
// Get JWT token from Supabase
const session = await supabase.auth.getSession();
const token = session.data.session?.access_token;

// Use it for MCP auth
const response = await fetch('/api/mcp/auth/providers', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
```

### OAuth Flow Example

```javascript
// 1. Start OAuth (with JWT)
async function connectProvider(provider) {
  const token = await getSupabaseToken();
  
  const response = await fetch(
    `/api/mcp/auth/${provider}/start?` +
    `redirect_success=${encodeURIComponent('/integrations/success')}&` +
    `redirect_error=${encodeURIComponent('/integrations/error')}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  const { authorization_url } = await response.json();
  
  // Open OAuth popup
  window.open(authorization_url, '_blank');
}

// 2. Callback is handled automatically
// Composio redirects to: /api/mcp/auth/{provider}/callback?user_id=xxx&code=...
// Server uses user_id from query (no JWT needed)
```

## Migration Guide

### Before (Legacy)
```javascript
// All requests used X-User-Id header
fetch('/api/mcp/auth/providers', {
  headers: { 'X-User-Id': userId }
});
```

### After (JWT Preferred)
```javascript
// Use JWT token (preferred)
fetch('/api/mcp/auth/providers', {
  headers: { 
    'Authorization': `Bearer ${jwtToken}`
  }
});

// Or still works with X-User-Id (backward compatible)
fetch('/api/mcp/auth/providers', {
  headers: { 'X-User-Id': userId }
});
```

## Security Considerations

### JWT Authentication (Secure)
- ✅ Token is cryptographically signed
- ✅ Token expiration enforced
- ✅ User identity verified
- ✅ No user_id spoofing possible

### Legacy X-User-Id (Less Secure)
- ⚠️ User can spoof `X-User-Id` header
- ⚠️ No expiration
- ⚠️ Still supported for OAuth callbacks

**Recommendation:** Use JWT tokens whenever possible. Legacy auth is maintained for:
1. OAuth callbacks (can't use JWT)
2. Backward compatibility during migration
3. Development/testing

## Debug Endpoints

These endpoints don't require authentication (for troubleshooting):

- `GET /api/mcp/auth/_debug/config` - Check auth configuration
- `GET /api/mcp/auth/_debug/ping` - Test Composio connectivity
- `GET /api/mcp/auth/_debug/auth-configs` - List auth configs
- `GET /api/mcp/auth/_debug/db` - Check database counts
- `GET /api/mcp/auth/_debug/mcp_client` - Test MCP client
- `GET /api/mcp/auth/_debug/connected-accounts` - List connected accounts

## Summary

| Aspect | JWT Auth | Legacy Auth |
|--------|----------|-------------|
| **Security** | ✅ High (cryptographic) | ⚠️ Low (spoofable) |
| **User ID Source** | Token `sub` claim | Header/query param |
| **Expiration** | ✅ Yes | ❌ No |
| **OAuth Callbacks** | ❌ Not possible | ✅ Required |
| **Recommended** | ✅ Yes | ⚠️ Only for callbacks |

**Best Practice:** Use JWT tokens for all frontend-initiated requests. Legacy auth is automatically used for OAuth callbacks from external providers.

