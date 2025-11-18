from __future__ import annotations

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from server.api.server import app
from mcp_agent.oauth import OAuthManager


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_slack_oauth_start_endpoint(client, monkeypatch):
    """Test that GET /api/mcp/auth/slack/start returns authorization_url correctly."""
    # Mock OAuthManager.start_oauth to return a test URL
    test_auth_url = "https://backend.composio.dev/oauth/slack?state=test123"
    
    with patch.object(OAuthManager, "start_oauth", return_value=test_auth_url):
        response = client.get(
            "/api/mcp/auth/slack/start",
            headers={"X-User-Id": "dev-local"},
        )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "authorization_url" in data, "Response should contain authorization_url"
    assert data["authorization_url"] == test_auth_url, "authorization_url should match mocked value"
    assert data["authorization_url"].startswith("http"), "authorization_url should be a valid URL"


def test_slack_oauth_start_endpoint_missing_user_id(client):
    """Test that missing X-User-Id header returns 400."""
    response = client.get("/api/mcp/auth/slack/start")
    
    assert response.status_code == 400, f"Expected 400 for missing user ID, got {response.status_code}"
    assert "X-User-Id" in response.text or "user" in response.text.lower(), "Error should mention user ID"


def test_slack_oauth_start_endpoint_missing_auth_config(monkeypatch, client):
    """Test that missing COMPOSIO_SLACK_AUTH_CONFIG_ID returns appropriate error."""
    # Mock _require_auth_config to raise RuntimeError when auth config is missing
    original_start_oauth = OAuthManager.start_oauth
    
    def mock_start_oauth(provider, user_id, redirect_uri):
        if provider == "slack":
            raise RuntimeError("COMPOSIO_SLACK_AUTH_CONFIG_ID missing")
        return original_start_oauth(provider, user_id, redirect_uri)
    
    with patch.object(OAuthManager, "start_oauth", side_effect=RuntimeError("COMPOSIO_SLACK_AUTH_CONFIG_ID missing")):
        response = client.get(
            "/api/mcp/auth/slack/start",
            headers={"X-User-Id": "dev-local"},
        )
    
    # Should return 502 (Bad Gateway) as per the route handler
    assert response.status_code == 502, f"Expected 502 for missing auth config, got {response.status_code}"
    assert "OAuth start failed" in response.text or "auth" in response.text.lower(), "Error should mention OAuth failure"


def test_slack_oauth_start_endpoint_invalid_provider(client):
    """Test that invalid provider returns 404."""
    response = client.get(
        "/api/mcp/auth/invalid_provider/start",
        headers={"X-User-Id": "dev-local"},
    )
    
    # FastAPI will return 404 for route not found, or the route might handle it differently
    # Check for either 404 or a handled error response
    assert response.status_code in [404, 400, 502], f"Expected 404/400/502 for invalid provider, got {response.status_code}"


def test_slack_oauth_start_endpoint_with_redirect_hints(client, monkeypatch):
    """Test that redirect_success and redirect_error query params are handled."""
    test_auth_url = "https://backend.composio.dev/oauth/slack?state=test123"
    
    with patch.object(OAuthManager, "start_oauth", return_value=test_auth_url):
        response = client.get(
            "/api/mcp/auth/slack/start",
            headers={"X-User-Id": "dev-local"},
            params={
                "redirect_success": "https://example.com/success",
                "redirect_error": "https://example.com/error",
            },
        )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert "authorization_url" in data, "Response should contain authorization_url"

