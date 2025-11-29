#!/bin/bash

# Test script for TakeBridge API endpoints
# Make sure server is running: uvicorn server.api.server:app --host 0.0.0.0 --port 8000

BASE_URL="https://localhost:8000"
CURL_OPTS="-k -s"  # -k for insecure SSL, -s for silent

echo "=== Testing TakeBridge API ==="
echo ""

echo "1. Testing /health (no auth required)..."
response=$(curl $CURL_OPTS "$BASE_URL/health")
echo "Response: $response"
if [[ "$response" == *"ok"* ]]; then
    echo "✓ Health check passed"
else
    echo "✗ Health check failed"
fi
echo ""

echo "2. Testing /debug/auth (no auth required)..."
response=$(curl $CURL_OPTS "$BASE_URL/debug/auth")
echo "Response: $response"
if [[ "$response" == *"jwt_secret_configured"* ]]; then
    echo "✓ Auth config check passed"
else
    echo "✗ Auth config check failed"
fi
echo ""

echo "3. Testing /orchestrate/stream without auth (should fail)..."
response=$(curl $CURL_OPTS "$BASE_URL/orchestrate/stream?task=test")
echo "Response: $response"
if [[ "$response" == *"Not authenticated"* ]]; then
    echo "✓ Auth protection working correctly"
else
    echo "✗ Auth protection not working"
fi
echo ""

echo "4. Testing /orchestrate/stream with invalid token (should fail)..."
response=$(curl $CURL_OPTS -H "Authorization: Bearer invalid-token" "$BASE_URL/orchestrate/stream?task=test")
echo "Response: $response"
if [[ "$response" == *"Invalid token"* ]] || [[ "$response" == *"Not authenticated"* ]]; then
    echo "✓ Invalid token rejection working"
else
    echo "✗ Invalid token rejection not working"
fi
echo ""

echo "=== Test Summary ==="
echo "To test with a valid token:"
echo "1. Generate token: python scripts/generate_test_token.py"
echo "2. Export: export JWT_TOKEN=\"your-token\""
echo "3. Test: curl -k -H \"Authorization: Bearer \$JWT_TOKEN\" $BASE_URL/app/workspace"

