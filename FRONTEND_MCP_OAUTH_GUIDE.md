# Frontend Guide: MCP OAuth Connection Buttons

Complete guide for implementing OAuth connection buttons for MCP providers (Gmail, Slack, etc.) in your frontend.

## Overview

This guide shows you how to:
1. Create connection buttons for providers
2. Handle OAuth flow with popups
3. Check connection status
4. Display connection state
5. Disconnect providers

## Prerequisites

- Supabase client configured
- API base URL configured
- JWT token available from Supabase session

## Setup

### 1. API Configuration

```javascript
// config.js
export const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.takebridge.com';

// Helper to get auth headers
export async function getAuthHeaders() {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    throw new Error('Not authenticated');
  }
  return {
    'Authorization': `Bearer ${session.access_token}`,
    'Content-Type': 'application/json'
  };
}
```

## Complete React Component Example

### ProviderConnectionButton Component

```jsx
import React, { useState, useEffect } from 'react';
import { supabase } from './supabase';
import { API_BASE_URL, getAuthHeaders } from './config';

function ProviderConnectionButton({ provider, displayName, icon }) {
  const [status, setStatus] = useState('loading'); // 'loading' | 'connected' | 'not_connected' | 'expired' | 'connecting'
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState(null);

  // Check connection status on mount and periodically
  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [provider]);

  const checkStatus = async () => {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${API_BASE_URL}/api/mcp/auth/${provider}/status/live`,
        { headers }
      );
      
      if (!response.ok) throw new Error('Failed to check status');
      
      const data = await response.json();
      
      if (data.authorized) {
        setStatus('connected');
      } else if (data.refresh_required) {
        setStatus('expired');
      } else {
        setStatus('not_connected');
      }
      setError(null);
    } catch (err) {
      console.error('Status check failed:', err);
      setStatus('not_connected');
    }
  };

  const handleConnect = async () => {
    setIsConnecting(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      
      // Build redirect URLs
      const redirectSuccess = `${window.location.origin}/integrations/success?provider=${provider}`;
      const redirectError = `${window.location.origin}/integrations/error?provider=${provider}`;
      
      // Start OAuth flow
      const response = await fetch(
        `${API_BASE_URL}/api/mcp/auth/${provider}/start?` +
        `redirect_success=${encodeURIComponent(redirectSuccess)}&` +
        `redirect_error=${encodeURIComponent(redirectError)}`,
        { headers }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start OAuth');
      }

      const { authorization_url } = await response.json();

      // Open OAuth popup
      const popup = window.open(
        authorization_url,
        `${provider}_oauth`,
        'width=600,height=700,scrollbars=yes,resizable=yes'
      );

      // Poll for popup closure and check status
      const pollTimer = setInterval(() => {
        if (popup.closed) {
          clearInterval(pollTimer);
          setIsConnecting(false);
          checkStatus(); // Recheck status after popup closes
        }
      }, 500);

      // Also listen for success message from popup
      window.addEventListener('message', handleOAuthMessage);

    } catch (err) {
      console.error('OAuth start failed:', err);
      setError(err.message);
      setIsConnecting(false);
    }
  };

  const handleOAuthMessage = (event) => {
    // Verify origin for security
    if (event.origin !== window.location.origin) return;
    
    if (event.data.type === 'oauth_success') {
      setIsConnecting(false);
      checkStatus();
      window.removeEventListener('message', handleOAuthMessage);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm(`Disconnect ${displayName}?`)) return;

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${API_BASE_URL}/api/mcp/auth/${provider}`,
        {
          method: 'DELETE',
          headers
        }
      );

      if (!response.ok) throw new Error('Failed to disconnect');
      
      setStatus('not_connected');
      setError(null);
    } catch (err) {
      console.error('Disconnect failed:', err);
      setError(err.message);
    }
  };

  const handleRefresh = async () => {
    setIsConnecting(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const redirectSuccess = `${window.location.origin}/integrations/success?provider=${provider}`;
      const redirectError = `${window.location.origin}/integrations/error?provider=${provider}`;
      
      const response = await fetch(
        `${API_BASE_URL}/api/mcp/auth/${provider}/refresh?` +
        `redirect_success=${encodeURIComponent(redirectSuccess)}&` +
        `redirect_error=${encodeURIComponent(redirectError)}`,
        {
          method: 'POST',
          headers
        }
      );

      if (!response.ok) throw new Error('Failed to refresh');

      const data = await response.json();
      
      if (data.authorization_url) {
        // Need to re-authorize
        const popup = window.open(
          data.authorization_url,
          `${provider}_oauth`,
          'width=600,height=700'
        );
        
        const pollTimer = setInterval(() => {
          if (popup.closed) {
            clearInterval(pollTimer);
            setIsConnecting(false);
            checkStatus();
          }
        }, 500);
      } else {
        // Refreshed in-place
        setIsConnecting(false);
        checkStatus();
      }
    } catch (err) {
      console.error('Refresh failed:', err);
      setError(err.message);
      setIsConnecting(false);
    }
  };

  const getButtonText = () => {
    if (isConnecting) return 'Connecting...';
    if (status === 'connected') return 'Connected';
    if (status === 'expired') return 'Reconnect';
    return `Connect ${displayName}`;
  };

  const getButtonStyle = () => {
    if (status === 'connected') {
      return {
        backgroundColor: '#10b981',
        color: 'white',
        border: 'none'
      };
    }
    if (status === 'expired') {
      return {
        backgroundColor: '#f59e0b',
        color: 'white',
        border: 'none'
      };
    }
    return {
      backgroundColor: '#3b82f6',
      color: 'white',
      border: 'none'
    };
  };

  return (
    <div className="provider-connection-card">
      <div className="provider-header">
        {icon && <span className="provider-icon">{icon}</span>}
        <h3>{displayName}</h3>
        {status === 'connected' && (
          <span className="status-badge connected">✓ Connected</span>
        )}
        {status === 'expired' && (
          <span className="status-badge expired">⚠ Expired</span>
        )}
      </div>

      {error && (
        <div className="error-message" style={{ color: 'red', marginBottom: '10px' }}>
          {error}
        </div>
      )}

      <div className="provider-actions">
        {status === 'connected' ? (
          <button
            onClick={handleDisconnect}
            style={{
              backgroundColor: '#ef4444',
              color: 'white',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            Disconnect
          </button>
        ) : status === 'expired' ? (
          <button
            onClick={handleRefresh}
            disabled={isConnecting}
            style={getButtonStyle()}
            className="connect-button"
          >
            {getButtonText()}
          </button>
        ) : (
          <button
            onClick={handleConnect}
            disabled={isConnecting}
            style={getButtonStyle()}
            className="connect-button"
          >
            {getButtonText()}
          </button>
        )}
      </div>
    </div>
  );
}

export default ProviderConnectionButton;
```

## Provider List Component

```jsx
import React, { useState, useEffect } from 'react';
import { supabase } from './supabase';
import { API_BASE_URL, getAuthHeaders } from './config';
import ProviderConnectionButton from './ProviderConnectionButton';

function ProviderList() {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProviders();
  }, []);

  const loadProviders = async () => {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${API_BASE_URL}/api/mcp/auth/providers`,
        { headers }
      );

      if (!response.ok) throw new Error('Failed to load providers');

      const data = await response.json();
      setProviders(data.providers || []);
    } catch (err) {
      console.error('Failed to load providers:', err);
    } finally {
      setLoading(false);
    }
  };

  const providerIcons = {
    gmail: '📧',
    slack: '💬',
    shopify: '🛒',
    github: '🐙',
    // Add more as needed
  };

  if (loading) {
    return <div>Loading providers...</div>;
  }

  return (
    <div className="providers-grid">
      {providers.map((provider) => (
        <ProviderConnectionButton
          key={provider.provider}
          provider={provider.provider}
          displayName={provider.display_name}
          icon={providerIcons[provider.provider]}
        />
      ))}
    </div>
  );
}

export default ProviderList;
```

## OAuth Callback Handler

Create pages to handle OAuth redirects:

### Success Page (`/integrations/success`)

```jsx
// pages/IntegrationsSuccess.jsx or components/IntegrationsSuccess.jsx
import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

function IntegrationsSuccess() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const provider = searchParams.get('provider');

  useEffect(() => {
    // Notify parent window if opened in popup
    if (window.opener) {
      window.opener.postMessage(
        { type: 'oauth_success', provider },
        window.location.origin
      );
      window.close();
    } else {
      // If not in popup, redirect after delay
      setTimeout(() => {
        navigate('/integrations');
      }, 2000);
    }
  }, [provider, navigate]);

  return (
    <div style={{ textAlign: 'center', padding: '40px' }}>
      <h2>✓ Successfully Connected!</h2>
      <p>{provider && `Your ${provider} account has been connected.`}</p>
      {!window.opener && <p>Redirecting...</p>}
    </div>
  );
}

export default IntegrationsSuccess;
```

### Error Page (`/integrations/error`)

```jsx
// pages/IntegrationsError.jsx
import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

function IntegrationsError() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const provider = searchParams.get('provider');
  const error = searchParams.get('error');

  useEffect(() => {
    if (window.opener) {
      window.opener.postMessage(
        { type: 'oauth_error', provider, error },
        window.location.origin
      );
      window.close();
    } else {
      setTimeout(() => {
        navigate('/integrations');
      }, 3000);
    }
  }, [provider, error, navigate]);

  return (
    <div style={{ textAlign: 'center', padding: '40px' }}>
      <h2 style={{ color: 'red' }}>✗ Connection Failed</h2>
      <p>{error || 'An error occurred during connection.'}</p>
      {!window.opener && <p>Redirecting...</p>}
    </div>
  );
}

export default IntegrationsError;
```

## Vanilla JavaScript Example

If you're not using React:

```javascript
// mcp-oauth.js
class MCPOAuthManager {
  constructor(apiBaseUrl, getAuthToken) {
    this.apiBaseUrl = apiBaseUrl;
    this.getAuthToken = getAuthToken;
  }

  async getAuthHeaders() {
    const token = await this.getAuthToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }

  async checkStatus(provider) {
    const headers = await this.getAuthHeaders();
    const response = await fetch(
      `${this.apiBaseUrl}/api/mcp/auth/${provider}/status/live`,
      { headers }
    );
    return response.json();
  }

  async connect(provider, onSuccess, onError) {
    try {
      const headers = await this.getAuthHeaders();
      const redirectSuccess = `${window.location.origin}/integrations/success?provider=${provider}`;
      const redirectError = `${window.location.origin}/integrations/error?provider=${provider}`;

      const response = await fetch(
        `${this.apiBaseUrl}/api/mcp/auth/${provider}/start?` +
        `redirect_success=${encodeURIComponent(redirectSuccess)}&` +
        `redirect_error=${encodeURIComponent(redirectError)}`,
        { headers }
      );

      if (!response.ok) throw new Error('Failed to start OAuth');

      const { authorization_url } = await response.json();

      // Open popup
      const popup = window.open(
        authorization_url,
        `${provider}_oauth`,
        'width=600,height=700'
      );

      // Poll for completion
      const pollTimer = setInterval(() => {
        if (popup.closed) {
          clearInterval(pollTimer);
          this.checkStatus(provider).then(onSuccess).catch(onError);
        }
      }, 500);

      // Listen for success message
      const messageHandler = (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data.type === 'oauth_success') {
          window.removeEventListener('message', messageHandler);
          onSuccess();
        }
      };
      window.addEventListener('message', messageHandler);

    } catch (error) {
      onError(error);
    }
  }

  async disconnect(provider) {
    const headers = await this.getAuthHeaders();
    const response = await fetch(
      `${this.apiBaseUrl}/api/mcp/auth/${provider}`,
      {
        method: 'DELETE',
        headers
      }
    );
    return response.json();
  }
}

// Usage
const oauthManager = new MCPOAuthManager(
  'https://api.takebridge.com',
  async () => {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token;
  }
);

// Create button
function createConnectButton(provider, displayName) {
  const button = document.createElement('button');
  button.textContent = `Connect ${displayName}`;
  button.className = 'connect-button';
  
  let status = 'not_connected';
  
  // Check initial status
  oauthManager.checkStatus(provider).then((data) => {
    if (data.authorized) {
      status = 'connected';
      button.textContent = 'Connected';
      button.style.backgroundColor = '#10b981';
    }
  });

  button.addEventListener('click', () => {
    if (status === 'connected') {
      if (confirm(`Disconnect ${displayName}?`)) {
        oauthManager.disconnect(provider).then(() => {
          status = 'not_connected';
          button.textContent = `Connect ${displayName}`;
          button.style.backgroundColor = '#3b82f6';
        });
      }
    } else {
      button.disabled = true;
      button.textContent = 'Connecting...';
      
      oauthManager.connect(
        provider,
        () => {
          status = 'connected';
          button.textContent = 'Connected';
          button.style.backgroundColor = '#10b981';
          button.disabled = false;
        },
        (error) => {
          alert(`Connection failed: ${error.message}`);
          button.textContent = `Connect ${displayName}`;
          button.disabled = false;
        }
      );
    }
  });

  return button;
}
```

## Styling Examples

### CSS for Provider Cards

```css
.providers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  padding: 20px;
}

.provider-connection-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  background: white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.provider-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.provider-icon {
  font-size: 24px;
}

.provider-header h3 {
  margin: 0;
  flex: 1;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.connected {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.expired {
  background: #fef3c7;
  color: #92400e;
}

.connect-button {
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.connect-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.connect-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-message {
  padding: 8px 12px;
  background: #fee2e2;
  border: 1px solid #fecaca;
  border-radius: 4px;
  color: #991b1b;
  font-size: 14px;
}
```

## Advanced: Real-time Status Updates

For better UX, use WebSockets or Server-Sent Events if available:

```jsx
// Real-time status with polling
useEffect(() => {
  const interval = setInterval(() => {
    checkStatus();
  }, 2000); // Poll every 2 seconds during connection

  return () => clearInterval(interval);
}, [status === 'connecting']);
```

## Error Handling

```jsx
const handleError = (error, context) => {
  console.error(`OAuth ${context} error:`, error);
  
  // Show user-friendly error
  const errorMessages = {
    'network': 'Network error. Please check your connection.',
    'auth': 'Authentication failed. Please log in again.',
    'oauth': 'OAuth connection failed. Please try again.',
    'timeout': 'Connection timed out. Please try again.'
  };

  setError(errorMessages[error.type] || error.message);
  
  // Log to error tracking service
  if (window.errorTracker) {
    window.errorTracker.captureException(error, { context });
  }
};
```

## Testing

```javascript
// Test OAuth flow
async function testOAuthFlow(provider) {
  console.log(`Testing ${provider} OAuth flow...`);
  
  // 1. Check initial status
  const initialStatus = await oauthManager.checkStatus(provider);
  console.log('Initial status:', initialStatus);
  
  // 2. Start connection
  await oauthManager.connect(
    provider,
    () => console.log('✓ Connection successful'),
    (err) => console.error('✗ Connection failed:', err)
  );
  
  // 3. Verify final status
  const finalStatus = await oauthManager.checkStatus(provider);
  console.log('Final status:', finalStatus);
}
```

## Summary

**Key Points:**
1. ✅ Use JWT tokens for all API calls
2. ✅ Open OAuth in popup window
3. ✅ Poll for popup closure or listen for messages
4. ✅ Handle success/error redirects
5. ✅ Show connection status with visual indicators
6. ✅ Provide disconnect functionality
7. ✅ Handle expired tokens with refresh flow

**Best Practices:**
- Always verify message origins for security
- Show loading states during connection
- Provide clear error messages
- Poll status periodically for real-time updates
- Handle popup blockers gracefully

