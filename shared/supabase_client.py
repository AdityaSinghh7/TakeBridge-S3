from __future__ import annotations

"""
Small helpers to initialize Supabase clients.

We keep two helpers:
- get_supabase_client(user_token): for user-scoped requests (RLS enforced by Supabase via JWT)
- get_service_supabase_client(): service role client for internal/worker paths (bypasses RLS)
"""

import os
from functools import lru_cache
from typing import Optional

from supabase import Client, create_client


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _check_env() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")
    if not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_ANON_KEY is not configured")
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not configured")


@lru_cache(maxsize=1)
def _base_anon_client() -> Client:
    _check_env()
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


@lru_cache(maxsize=1)
def _base_service_client() -> Client:
    _check_env()
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def get_supabase_client(user_token: Optional[str] = None) -> Client:
    """
    Return an anon-key client authenticated with a user's JWT for RLS.
    """
    client = _base_anon_client()
    if user_token:
        client.postgrest.auth(user_token)
    return client


def get_service_supabase_client() -> Client:
    """
    Return a service-role client (bypasses RLS). Use only for trusted paths.
    """
    return _base_service_client()


__all__ = ["get_supabase_client", "get_service_supabase_client"]
