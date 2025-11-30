# Quick Start: MCP OAuth Button

Minimal example to get started quickly.

## Simple React Button Component

```jsx
import { useState, useEffect } from 'react';
import { supabase } from './supabase'; // Your Supabase client

function ConnectButton({ provider, name }) {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const API_URL = 'https://api.takebridge.com';

  // Check if already connected
  useEffect(() => {
    checkStatus();
  }, []);

  const checkStatus = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const response = await fetch(
        `${API_URL}/api/mcp/auth/${provider}/status/live`,
        {
          headers: { 'Authorization': `Bearer ${session.access_token}` }
        }
      );
      const data = await response.json();
      setConnected(data.authorized || false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleClick = async () => {
    if (connected) {
      // Disconnect
      if (!confirm(`Disconnect ${name}?`)) return;
      try {
        const { data: { session } } = await supabase.auth.getSession();
        await fetch(`${API_URL}/api/mcp/auth/${provider}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${session.access_token}` }
        });
        setConnected(false);
      } catch (err) {
        alert('Failed to disconnect');
      }
    } else {
      // Connect
      setLoading(true);
      try {
        const { data: { session } } = await supabase.auth.getSession();
        const successUrl = `${window.location.origin}/oauth-success?provider=${provider}`;
        const errorUrl = `${window.location.origin}/oauth-error?provider=${provider}`;
        
        const response = await fetch(
          `${API_URL}/api/mcp/auth/${provider}/start?` +
          `redirect_success=${encodeURIComponent(successUrl)}&` +
          `redirect_error=${encodeURIComponent(errorUrl)}`,
          {
            headers: { 'Authorization': `Bearer ${session.access_token}` }
          }
        );
        
        const { authorization_url } = await response.json();
        
        // Open OAuth popup
        const popup = window.open(authorization_url, 'oauth', 'width=600,height=700');
        
        // Check when popup closes
        const checkClosed = setInterval(() => {
          if (popup.closed) {
            clearInterval(checkClosed);
            setLoading(false);
            checkStatus(); // Recheck connection status
          }
        }, 500);
      } catch (err) {
        alert('Failed to start connection');
        setLoading(false);
      }
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      style={{
        padding: '10px 20px',
        backgroundColor: connected ? '#10b981' : '#3b82f6',
        color: 'white',
        border: 'none',
        borderRadius: '6px',
        cursor: loading ? 'wait' : 'pointer'
      }}
    >
      {loading ? 'Connecting...' : connected ? `✓ ${name} Connected` : `Connect ${name}`}
    </button>
  );
}

// Usage
function App() {
  return (
    <div>
      <ConnectButton provider="gmail" name="Gmail" />
      <ConnectButton provider="slack" name="Slack" />
    </div>
  );
}
```

## OAuth Success/Error Pages

Create these pages to handle OAuth redirects:

**`/oauth-success` page:**
```jsx
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

export default function OAuthSuccess() {
  const [params] = useSearchParams();
  
  useEffect(() => {
    // Close popup if opened in popup
    if (window.opener) {
      window.opener.postMessage({ type: 'oauth_success' }, window.location.origin);
      window.close();
    }
  }, []);

  return <div>✓ Successfully connected!</div>;
}
```

**`/oauth-error` page:**
```jsx
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

export default function OAuthError() {
  const [params] = useSearchParams();
  const error = params.get('error');
  
  useEffect(() => {
    if (window.opener) {
      window.opener.postMessage({ type: 'oauth_error', error }, window.location.origin);
      window.close();
    }
  }, [error]);

  return <div>✗ Connection failed: {error}</div>;
}
```

## That's It!

1. Copy the `ConnectButton` component
2. Create success/error pages
3. Use it: `<ConnectButton provider="gmail" name="Gmail" />`

For more details, see `FRONTEND_MCP_OAUTH_GUIDE.md`.

