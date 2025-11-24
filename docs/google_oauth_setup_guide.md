# Google OAuth Setup for Composio Gmail Integration

## Step 1: Access Google Cloud Console

Go to: https://console.cloud.google.com/

## Step 2: Select or Create a Project

1. Click the project dropdown at the top
2. Either:
   - **Use existing project**: Select your project
   - **Create new project**: Click "New Project"
     - Name: "TakeBridge Production" (or whatever)
     - Click "Create"

## Step 3: Enable Gmail API

1. Go to: https://console.cloud.google.com/apis/library/gmail.googleapis.com
2. Click "**Enable**"
3. Wait for it to enable (5-10 seconds)

## Step 4: Create OAuth Consent Screen (if not already done)

1. Go to: https://console.cloud.google.com/apis/credentials/consent
2. Choose:
   - **External** (if this is for external users)
   - **Internal** (if only for your organization's G Suite domain)
3. Fill out the form:
   - **App name**: TakeBridge
   - **User support email**: your-email@example.com
   - **Developer contact**: your-email@example.com
   - Click "Save and Continue"
4. **Scopes**:
   - Click "Add or Remove Scopes"
   - Add these scopes:
     - `https://mail.google.com/` (Full Gmail access)
     - `https://www.googleapis.com/auth/userinfo.email` (Email address)
     - `https://www.googleapis.com/auth/userinfo.profile` (Basic profile)
   - Click "Update" → "Save and Continue"
5. **Test users** (if External):
   - Add your Gmail address as a test user
   - Click "Save and Continue"
6. **Summary**:
   - Review and click "Back to Dashboard"

## Step 5: Create OAuth 2.0 Client ID

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click "**+ Create Credentials**" → "**OAuth client ID**"
3. Configure:
   - **Application type**: Web application
   - **Name**: TakeBridge Gmail Integration
   - **Authorized JavaScript origins**: (leave empty)
   - **Authorized redirect URIs**: Add BOTH of these:
     ```
     https://localhost:8000/api/composio-redirect
     https://backend.composio.dev/api/v1/integrations/oauth/callback
     ```
   - Click "**Create**"

4. **COPY YOUR CREDENTIALS** (save these somewhere safe):
   ```
   Client ID: 871159898466-xxxxxxxxxxxxx.apps.googleusercontent.com
   Client Secret: GOCSPX-xxxxxxxxxxxxxxxx
   ```

## Step 6: Configure in Composio Dashboard

1. Go to: https://app.composio.dev
2. Navigate to:
   - **Settings** → **Auth Configs** (or similar)
   - OR **Integrations** → **Gmail** → **Auth Configs**
3. Find auth config: **`ac__kYlScI5FgLX`**
4. Click "**Edit**" or "**Configure**"
5. Add these values:

   | Field | Value |
   |-------|-------|
   | **Client ID** | `<your-client-id-from-step-5>` |
   | **Client Secret** | `<your-client-secret-from-step-5>` |
   | **Authorization URL** | `https://accounts.google.com/o/oauth2/auth` |
   | **Token URL** | `https://oauth2.googleapis.com/token` |
   | **Scopes** | `https://mail.google.com/ openid email profile` |

6. Click "**Save**"

## Step 7: Re-enable Auth Config in Your .env

After configuring in Composio dashboard, uncomment this line in your `.env`:

```bash
# Change this:
# COMPOSIO_GMAIL_AUTH_CONFIG_ID=ac__kYlScI5FgLX  # Disabled: custom config missing OAuth app credentials

# To this:
COMPOSIO_GMAIL_AUTH_CONFIG_ID=ac__kYlScI5FgLX
```

## Step 8: Reconnect Gmail

Run these commands:

```bash
# Delete old broken connection
python3 scripts/delete_gmail_account.py

# Start fresh OAuth flow (will use your newly configured auth config)
python3 scripts/fix_gmail_auth.py

# Follow the OAuth flow in your browser
# Then finalize the connection as instructed

# Test it works
python3 scripts/probe_tools.py
```

## Troubleshooting

### Error: "Access blocked: This app's request is invalid"
- Check that you added the correct redirect URIs in Step 5
- Make sure both URIs are added:
  - `https://localhost:8000/api/composio-redirect`
  - `https://backend.composio.dev/api/v1/integrations/oauth/callback`

### Error: "The OAuth client was not found"
- Verify the Client ID and Client Secret are correct
- Make sure you copied them from the same OAuth client

### Error: "Access denied"
- Make sure Gmail API is enabled (Step 3)
- Check that you added the required scopes (Step 4)
- If using External user type, make sure your email is added as a test user

### Still getting "credentials do not contain necessary fields" error
- Double-check that ALL fields are filled in Composio auth config:
  - Client ID
  - Client Secret
  - Token URL (`https://oauth2.googleapis.com/token`)
  - Authorization URL (`https://accounts.google.com/o/oauth2/auth`)
- The token URL is critical - this is what was missing before

## Quick Reference: What Credentials Are Needed

```json
{
  "client_id": "871159898466-xxxxx.apps.googleusercontent.com",
  "client_secret": "GOCSPX-xxxxxxxx",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "scopes": [
    "https://mail.google.com/",
    "openid",
    "email",
    "profile"
  ]
}
```

The `token_uri` is what allows Google's OAuth library to refresh expired access tokens. This is what was missing from your auth config before!
