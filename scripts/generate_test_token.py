#!/usr/bin/env python3
"""
Generate a test JWT token for local testing.

Usage:
    python scripts/generate_test_token.py [user_id] [email]

Example:
    python scripts/generate_test_token.py test-user-123 test@example.com
"""

import sys
import time
import os
from jose import jwt
from dotenv import load_dotenv

load_dotenv()

def generate_test_token(user_id: str = "test-user-123", email: str = "test@example.com", expires_in: int = 3600):
    """Generate a test JWT token compatible with Supabase."""
    secret = os.getenv("SUPABASE_JWT_SECRET")
    
    if not secret:
        print("ERROR: SUPABASE_JWT_SECRET not found in environment variables")
        print("Please set it in your .env file or export it:")
        print("  export SUPABASE_JWT_SECRET='your-secret-here'")
        sys.exit(1)
    
    now = int(time.time())
    
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token

if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else "test-user-123"
    email = sys.argv[2] if len(sys.argv) > 2 else "test@example.com"
    
    token = generate_test_token(user_id, email)
    
    print("=" * 60)
    print("Test JWT Token Generated")
    print("=" * 60)
    print(f"User ID: {user_id}")
    print(f"Email: {email}")
    print(f"Token (expires in 1 hour):")
    print(token)
    print("=" * 60)
    print("\nUse it in curl like this:")
    print(f'curl -H "Authorization: Bearer {token}" \\')
    print("  http://localhost:8000/app/workspace")
    print("\nOr save to environment variable:")
    print(f'export JWT_TOKEN="{token}"')

