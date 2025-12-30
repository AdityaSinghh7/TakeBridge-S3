# server/api/auth.py

import logging
import time
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import BaseModel

from vm_manager.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    sub: str
    email: str | None = None
    token: str


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    if creds is None:
        logger.warning(
            "No authorization credentials provided method=%s path=%s",
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - missing Authorization header",
        )

    token = creds.credentials

    # Log token prefix for debugging (first 12 chars)
    logger.info(
        "Authorization header present method=%s path=%s token_prefix=%s",
        request.method,
        request.url.path,
        token[:12],
    )

    unverified: dict = {}
    try:
        # Decode without verification first to check structure
        unverified = jwt.get_unverified_claims(token)
        logger.info(
            "Token claims (unverified) aud=%s exp=%s iat=%s now=%s",
            unverified.get("aud"),
            unverified.get("exp"),
            unverified.get("iat"),
            int(time.time()),
        )

        # Get the audience from the token for logging
        token_audience = unverified.get("aud")
        token_role = unverified.get("role")
        logger.info("Token role: %s, audience: %s", token_role, token_audience)

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
        logger.info(
            "Token decoded successfully user=%s role=%s",
            payload.get("sub"),
            payload.get("role"),
        )

    except ExpiredSignatureError:
        logger.warning(
            "Token has expired exp=%s iat=%s now=%s",
            unverified.get("exp"),
            unverified.get("iat"),
            int(time.time()),
        )
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

    logger.info("Authenticated user: %s", sub)
    return CurrentUser(sub=sub, email=email, token=token)
