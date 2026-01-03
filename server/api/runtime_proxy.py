from __future__ import annotations

import os
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

RUNTIME_BASE_URL = os.getenv("RUNTIME_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
RUNTIME_VERIFY_SSL = os.getenv("RUNTIME_VERIFY_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}
RUNTIME_CA_BUNDLE = os.getenv("RUNTIME_CA_BUNDLE") or os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE")

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def _build_verify() -> object:
    if RUNTIME_CA_BUNDLE:
        return RUNTIME_CA_BUNDLE
    return RUNTIME_VERIFY_SSL


def _should_trust_env(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return hostname not in {"127.0.0.1", "localhost"}
    except Exception:
        return True


def _forward_headers(headers: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    forwarded: Dict[str, str] = {}
    for key, value in headers:
        if key.lower() in _HOP_BY_HOP:
            continue
        forwarded[key] = value
    return forwarded


def _response_headers(resp: httpx.Response) -> Dict[str, str]:
    keep = {"content-type", "cache-control", "x-accel-buffering"}
    return {k: v for k, v in resp.headers.items() if k.lower() in keep}


async def proxy_request(
    request: Request,
    *,
    stream: bool,
    body: Optional[bytes] = None,
    path_override: Optional[str] = None,
    headers_override: Optional[Dict[str, str]] = None,
) -> Response | StreamingResponse:
    path = path_override or request.url.path
    url = f"{RUNTIME_BASE_URL}{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    payload = body if body is not None else await request.body()
    headers = headers_override or _forward_headers(request.headers.items())

    client = httpx.AsyncClient(
        timeout=None,
        verify=_build_verify(),
        trust_env=_should_trust_env(url),
    )
    if stream:
        req = client.build_request(request.method, url, headers=headers, content=payload)
        resp = await client.send(req, stream=True)
        if resp.status_code >= 400:
            detail = await resp.aread()
            await resp.aclose()
            await client.aclose()
            raise HTTPException(status_code=resp.status_code, detail=detail.decode("utf-8", "ignore"))

        async def _iter():
            try:
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(
            _iter(),
            status_code=resp.status_code,
            headers=_response_headers(resp),
            media_type=resp.headers.get("content-type"),
        )

    resp = await client.request(
        request.method,
        url,
        headers=headers,
        content=payload,
    )
    if resp.status_code >= 400:
        detail = resp.text
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=resp.status_code, detail=detail)
    content = resp.content
    media_type = resp.headers.get("content-type")
    headers_out = _response_headers(resp)
    await resp.aclose()
    await client.aclose()
    return Response(content=content, status_code=resp.status_code, media_type=media_type, headers=headers_out)


def proxy_request_sync(
    method: str,
    path: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    json_body: Optional[object] = None,
    stream: bool = False,
) -> Response | StreamingResponse:
    url = f"{RUNTIME_BASE_URL}{path}"
    verify = _build_verify()
    trust_env = _should_trust_env(url)
    headers = _forward_headers((k, v) for k, v in (headers or {}).items())

    client = httpx.Client(timeout=None, verify=verify, trust_env=trust_env)
    if stream:
        req = client.build_request(method, url, headers=headers, params=params, json=json_body)
        resp = client.send(req, stream=True)
        if resp.status_code >= 400:
            detail = resp.read().decode("utf-8", "ignore")
            resp.close()
            client.close()
            raise HTTPException(status_code=resp.status_code, detail=detail)

        def _iter():
            try:
                for chunk in resp.iter_bytes():
                    if chunk:
                        yield chunk
            finally:
                resp.close()
                client.close()

        return StreamingResponse(
            _iter(),
            status_code=resp.status_code,
            headers=_response_headers(resp),
            media_type=resp.headers.get("content-type"),
        )

    resp = client.request(method, url, headers=headers, params=params, json=json_body)
    if resp.status_code >= 400:
        detail = resp.text
        client.close()
        raise HTTPException(status_code=resp.status_code, detail=detail)
    content = resp.content
    media_type = resp.headers.get("content-type")
    headers_out = _response_headers(resp)
    client.close()
    return Response(content=content, status_code=resp.status_code, media_type=media_type, headers=headers_out)
