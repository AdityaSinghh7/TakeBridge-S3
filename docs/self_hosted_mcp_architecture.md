# Self-Hosted MCP + OAuth Architecture

## Overview

This document outlines what it would take to replace Composio with a self-hosted solution.

## Architecture Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application                          │
│  (Agent, runs sandbox code, calls MCP servers)              │
└─────────────┬───────────────────────────────────────────────┘
              │
              │ HTTP/MCP Protocol
              ▼
┌─────────────────────────────────────────────────────────────┐
│                  MCP Server (Self-Hosted)                    │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  MCP Protocol Handler                          │         │
│  │  - list_tools()                                │         │
│  │  - call_tool(name, params)                     │         │
│  └────────────────┬───────────────────────────────┘         │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────┐         │
│  │  OAuth Manager                                 │         │
│  │  - Get credentials for user                    │         │
│  │  - Refresh tokens if expired                   │         │
│  └────────────────┬───────────────────────────────┘         │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────┐         │
│  │  Provider API Clients                          │         │
│  │  - gmail.py                                    │         │
│  │  - slack.py                                    │         │
│  │  - shopify.py                                  │         │
│  │  (Direct API calls with OAuth tokens)         │         │
│  └────────────────┬───────────────────────────────┘         │
└───────────────────┼──────────────────────────────────────────┘
                    │
                    │ HTTPS + OAuth Bearer Token
                    ▼
          ┌──────────────────────┐
          │   Provider APIs      │
          │  (Gmail, Slack, etc) │
          └──────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 OAuth Web Service                            │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  OAuth Endpoints                               │         │
│  │  GET  /oauth/authorize/:provider               │         │
│  │  GET  /oauth/callback/:provider                │         │
│  │  POST /oauth/refresh/:provider                 │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  Credential Storage (Encrypted)                │         │
│  │  - PostgreSQL with encryption at rest          │         │
│  │  - Table: oauth_credentials                    │         │
│  │    * user_id                                   │         │
│  │    * provider                                  │         │
│  │    * access_token (encrypted)                  │         │
│  │    * refresh_token (encrypted)                 │         │
│  │    * expires_at                                │         │
│  └────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. MCP Server (Reusable)

**What it does:** Exposes your provider tools via MCP protocol

**Implementation:**
```python
# mcp_server/server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List

app = FastAPI()

class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any]
    user_id: str

@app.get("/tools")
async def list_tools():
    """List all available tools across all providers."""
    return {
        "tools": [
            {
                "name": "gmail_search",
                "description": "Search Gmail messages",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"}
                    }
                }
            },
            # ... more tools
        ]
    }

@app.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    """Execute a tool with OAuth credentials."""
    from mcp_server.oauth_manager import OAuthManager
    from mcp_server.providers import get_provider_client

    # Get fresh credentials
    credentials = await OAuthManager.get_credentials(
        user_id=request.user_id,
        provider=extract_provider(request.name)
    )

    # Call provider API
    client = get_provider_client(request.name)
    result = await client.execute(credentials, request.arguments)

    return result
```

**Effort:** 1-2 weeks for basic implementation

---

### 2. OAuth Manager (Reusable Core + Provider-Specific Config)

**What it does:** Manages OAuth flows, token storage, and refresh

#### 2.1 Core OAuth Flow (Reusable)

```python
# mcp_server/oauth_manager.py
from authlib.integrations.starlette_client import OAuth
from cryptography.fernet import Fernet
import json

class OAuthManager:
    """Reusable OAuth 2.0 manager."""

    PROVIDERS = {
        "gmail": {
            "client_id": "YOUR_GOOGLE_CLIENT_ID",
            "client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
            "authorize_url": "https://accounts.google.com/o/oauth2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": ["https://mail.google.com/"],
        },
        "slack": {
            "client_id": "YOUR_SLACK_CLIENT_ID",
            "client_secret": "YOUR_SLACK_CLIENT_SECRET",
            "authorize_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "scopes": ["chat:write", "channels:read"],
        },
        # Add more providers...
    }

    def __init__(self, db, encryption_key: bytes):
        self.db = db
        self.cipher = Fernet(encryption_key)
        self.oauth = OAuth()

        # Register all providers
        for name, config in self.PROVIDERS.items():
            self.oauth.register(
                name=name,
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                authorize_url=config["authorize_url"],
                access_token_url=config["token_url"],
                client_kwargs={"scope": " ".join(config["scopes"])},
            )

    async def start_oauth(self, provider: str, user_id: str, redirect_uri: str):
        """Start OAuth flow, return authorization URL."""
        client = self.oauth.create_client(provider)
        return await client.authorize_redirect(
            redirect_uri,
            state=f"{user_id}:{provider}"  # Encode user info in state
        )

    async def handle_callback(self, provider: str, code: str, state: str):
        """Handle OAuth callback, store credentials."""
        user_id, provider_name = state.split(":")

        # Exchange code for tokens
        client = self.oauth.create_client(provider)
        token = await client.fetch_token(
            authorization_response=request.url,
            code=code
        )

        # Encrypt and store
        encrypted_access = self.cipher.encrypt(token["access_token"].encode())
        encrypted_refresh = self.cipher.encrypt(token.get("refresh_token", "").encode())

        await self.db.execute("""
            INSERT INTO oauth_credentials
            (user_id, provider, access_token, refresh_token, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at
        """, user_id, provider, encrypted_access, encrypted_refresh,
            token["expires_at"])

    async def get_credentials(self, user_id: str, provider: str):
        """Get valid credentials, refreshing if needed."""
        row = await self.db.fetchrow("""
            SELECT access_token, refresh_token, expires_at
            FROM oauth_credentials
            WHERE user_id = $1 AND provider = $2
        """, user_id, provider)

        if not row:
            raise Exception(f"No credentials for {user_id}/{provider}")

        # Decrypt
        access_token = self.cipher.decrypt(row["access_token"]).decode()
        refresh_token = self.cipher.decrypt(row["refresh_token"]).decode()

        # Check if expired
        import time
        if row["expires_at"] < time.time():
            # Refresh token
            access_token, refresh_token = await self.refresh_token(
                provider, refresh_token
            )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def refresh_token(self, provider: str, refresh_token: str):
        """Refresh an expired access token."""
        config = self.PROVIDERS[provider]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                }
            )
            token = response.json()

            # Update storage
            # ... (similar to handle_callback)

            return token["access_token"], token.get("refresh_token", refresh_token)
```

**Effort:**
- Core OAuth flow: **1 week**
- Provider configs: **30 mins per provider** × 30 providers = **15 hours**

#### 2.2 Provider-Specific Quirks (NOT Reusable)

Despite OAuth 2.0 being "standard", each provider has quirks:

| Provider | Quirk |
|----------|-------|
| **Gmail** | Uses Google's OAuth, requires specific scopes, tokens expire in 1 hour |
| **Slack** | Returns `authed_user` vs `bot` tokens, workspace-scoped |
| **Shopify** | Shop-specific OAuth (need shop domain), offline access tokens |
| **Stripe** | Uses `stripe_user_id` for connected accounts |
| **Salesforce** | Instance-specific token URLs, sandbox vs production |
| **QuickBooks** | Tokens expire in 1 hour, refresh tokens expire in 100 days |
| **Notion** | Workspace-level OAuth, different token structure |
| **Xero** | Tenant selection after OAuth, multiple orgs per user |

**Example: Slack's quirk**
```python
# Slack returns nested token structure
{
  "ok": true,
  "access_token": "xoxb-...",  # Bot token
  "authed_user": {
    "access_token": "xoxp-..."  # User token
  }
}
# You need to decide which one to use!
```

**Example: Shopify's quirk**
```python
# Shopify needs shop domain in OAuth flow
authorize_url = f"https://{shop_domain}/admin/oauth/authorize"
token_url = f"https://{shop_domain}/admin/oauth/access_token"
# Different URL per customer!
```

**Effort:** **2-4 hours per provider** to handle quirks = **60-120 hours total**

---

### 3. Provider API Clients (Per-Provider Work)

**What it does:** Makes actual API calls to Gmail, Slack, etc.

Each provider needs a client that:
1. Takes OAuth credentials
2. Makes HTTP requests with proper auth headers
3. Handles provider-specific errors
4. Parses responses

**Example: Gmail Client**
```python
# mcp_server/providers/gmail.py
import httpx
from typing import Dict, Any, List

class GmailClient:
    """Gmail API client."""

    BASE_URL = "https://www.googleapis.com/gmail/v1"

    async def search_messages(
        self,
        credentials: Dict[str, str],
        query: str = "",
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search Gmail messages."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/users/me/messages",
                headers={
                    "Authorization": f"Bearer {credentials['access_token']}"
                },
                params={
                    "q": query,
                    "maxResults": max_results,
                }
            )

            if response.status_code == 401:
                # Token expired, need refresh
                raise TokenExpiredError()

            response.raise_for_status()
            data = response.json()

            # Fetch full message details
            messages = []
            for msg in data.get("messages", []):
                msg_detail = await self.get_message(credentials, msg["id"])
                messages.append(msg_detail)

            return messages

    async def send_email(
        self,
        credentials: Dict[str, str],
        to: str,
        subject: str,
        body: str
    ) -> Dict[str, Any]:
        """Send an email via Gmail API."""
        # Construct MIME message
        from email.mime.text import MIMEText
        import base64

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/users/me/messages/send",
                headers={
                    "Authorization": f"Bearer {credentials['access_token']}",
                    "Content-Type": "application/json"
                },
                json={"raw": raw}
            )

            response.raise_for_status()
            return response.json()
```

**Effort per provider:**
- Simple APIs (Slack, Stripe): **1-2 days**
- Medium APIs (Gmail, Shopify): **3-4 days**
- Complex APIs (Salesforce, QuickBooks): **5-7 days**

**Total for 30 providers:** **90-150 days** (can be parallelized)

---

### 4. Database Schema

```sql
-- OAuth credentials storage
CREATE TABLE oauth_credentials (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    access_token BYTEA NOT NULL,  -- Encrypted
    refresh_token BYTEA,  -- Encrypted
    expires_at BIGINT NOT NULL,
    scopes TEXT[],
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

-- OAuth apps configuration
CREATE TABLE oauth_apps (
    id SERIAL PRIMARY KEY,
    provider TEXT UNIQUE NOT NULL,
    client_id TEXT NOT NULL,
    client_secret_encrypted BYTEA NOT NULL,
    authorize_url TEXT NOT NULL,
    token_url TEXT NOT NULL,
    scopes TEXT[] NOT NULL,
    metadata JSONB
);

-- Audit log
CREATE TABLE oauth_events (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- 'authorize', 'refresh', 'revoke'
    success BOOLEAN NOT NULL,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Effort:** **1 day** for schema design and migrations

---

## Step-by-Step Implementation Plan

### Phase 1: Core Infrastructure (2-3 weeks)

1. **Set up MCP server** (3 days)
   - FastAPI app with `/tools` and `/tools/call` endpoints
   - Basic request/response handling
   - Error handling

2. **Implement OAuth manager** (5 days)
   - Core OAuth 2.0 flow (authorize, callback, refresh)
   - Database integration
   - Encryption at rest
   - Token refresh automation

3. **Build 1-2 pilot providers** (5 days)
   - Gmail + Slack as proof of concept
   - Full API client implementation
   - Integration with OAuth manager

4. **Testing & deployment** (2 days)
   - Unit tests
   - Integration tests
   - Docker deployment

### Phase 2: Scale to All Providers (4-8 weeks)

5. **Add remaining providers** (6-8 weeks, can parallelize)
   - Implement API clients for all 30 providers
   - Handle provider-specific quirks
   - Add tool schemas

6. **Production hardening** (1 week)
   - Rate limiting
   - Monitoring/alerting
   - Error tracking
   - Token refresh background jobs

### Phase 3: Feature Parity (1-2 weeks)

7. **Additional features**
   - Multi-workspace support (Slack teams, Shopify shops)
   - Credential health checks
   - OAuth scope management
   - Admin dashboard

---

## Reusability Analysis

### Highly Reusable (Build Once)
✅ MCP server protocol implementation
✅ OAuth 2.0 core flow (authorize, callback, refresh)
✅ Encryption/decryption logic
✅ Database schema
✅ Token refresh automation
✅ HTTP client utilities

### Somewhat Reusable (Configure Per Provider)
⚠️ OAuth configuration (URLs, scopes) - **15 hours total**
⚠️ Provider quirks handling - **60-120 hours total**

### NOT Reusable (Per-Provider Work)
❌ API client implementation - **90-150 days total**
❌ Tool schema definitions - **30 hours total**
❌ Response parsing/normalization - **included in API client**

---

## Total Effort Estimate

| Component | Effort | Parallelizable? |
|-----------|--------|-----------------|
| MCP server core | 1-2 weeks | No |
| OAuth manager core | 1 week | No |
| Database setup | 1 day | No |
| Provider configs | 15 hours | Yes |
| Provider quirks | 60-120 hours | Yes |
| API clients (30 providers) | 90-150 days | **Yes** |
| Testing & hardening | 1 week | No |
| **Total (1 person)** | **4-6 months** | - |
| **Total (3 people)** | **2-3 months** | - |

---

## Cost-Benefit Analysis

### Building Your Own
**Pros:**
- Full control over infrastructure
- No per-request costs (Composio charges per API call)
- Custom features/integrations
- Data sovereignty (credentials stay on your infra)

**Cons:**
- Large upfront time investment (2-6 months)
- Ongoing maintenance burden
- Security responsibility (credential storage, encryption)
- Need to handle provider API changes

### Using Composio
**Pros:**
- **Immediate availability** (already working)
- Provider updates handled automatically
- Battle-tested OAuth flows
- No security burden

**Cons:**
- Vendor lock-in
- Per-request pricing
- Less control over infrastructure
- Current auth config issue you're facing

---

## Recommendation

Given your current state:

### Short Term (1-2 days)
Fix the Composio auth config issue:
1. Add OAuth app credentials to `ac__kYlScI5FgLX`, OR
2. Switch to a Composio-managed auth config

This unblocks you immediately.

### Medium Term (1-3 months)
If cost/control becomes important:
1. Build self-hosted MCP infrastructure
2. Start with 3-5 critical providers (Gmail, Slack, Shopify)
3. Gradually migrate providers over time
4. Run hybrid: Composio for some, self-hosted for others

### Long Term (3-6 months)
If you need full control:
1. Complete self-hosted implementation for all providers
2. Deprecate Composio entirely
3. Build custom features on top

---

## Key Takeaways

1. **OAuth 2.0 core IS reusable** - Build once, configure per provider (~1 week)
2. **Provider quirks are NOT reusable** - Each needs custom handling (60-120 hours)
3. **API clients are NOT reusable** - Each provider is unique (90-150 days)
4. **Main effort is API client development** - This is the bulk of the work
5. **Parallelizable** - With 3 developers, 2-3 months is realistic

The question is: **Is 2-6 months of engineering time worth it to replace Composio?**

For most teams: **No, fix the auth config first**
For teams with specific needs: **Yes, but start small (3-5 providers)**
