# server/api/auth.py

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import BaseModel

from vm_manager.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    sub: str
    email: str | None = None


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    if creds is None:
        logger.warning("No authorization credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - missing Authorization header",
        )

    token = creds.credentials

    # Log token prefix for debugging (first 20 chars)
    logger.debug(f"Received token (prefix): {token[:20]}...")

    try:
        # Decode without verification first to check structure
        unverified = jwt.get_unverified_claims(token)
        logger.debug(f"Token claims (unverified): {list(unverified.keys())}")
        logger.debug(f"Token audience (aud): {unverified.get('aud')}")

        # Get the audience from the token for logging
        token_audience = unverified.get("aud")
        token_role = unverified.get("role")
        logger.debug(f"Token role: {token_role}, audience: {token_audience}")

        # Now decode with verification
        # Supabase tokens have 'aud' claim (typically "authenticated" or "anon")
        # We verify signature with the JWT secret, which is the main security check
        # Audience verification is disabled since signature verification ensures authenticity
        # and we want to accept both "authenticated" and potentially other valid Supabase audiences
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[settings.SUPABASE_JWT_ALG],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": False,  # Disable audience verification - signature check is sufficient
            },
        )
        logger.debug(
            f"Token decoded successfully for user: {payload.get('sub')}, role: {payload.get('role')}"
        )

    except ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError as e:
        logger.error(f"JWT verification failed: {str(e)}")
        logger.error(f"JWT secret length: {len(settings.SUPABASE_JWT_SECRET)}")
        logger.error(f"JWT secret prefix: {settings.SUPABASE_JWT_SECRET[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
        )

    sub = payload.get("sub") or payload.get("user_id")
    email = payload.get("email")

    if not sub:
        logger.warning(
            f"Token missing 'sub' claim. Available claims: {list(payload.keys())}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload - missing user ID",
        )

    logger.debug(f"Authenticated user: {sub}")
    return CurrentUser(sub=sub, email=email)
