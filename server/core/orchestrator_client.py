# server/core/orchestrator_client.py

import httpx

from server.api.config import settings


class OrchestratorClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = base_url or settings.ORCHESTRATOR_BASE_URL
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, verify=False)
        return self._client

    async def orchestrate(self, payload: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}/orchestrate"
        timeout = httpx.Timeout(
            settings.ORCHESTRATOR_TIMEOUT_SECONDS,
            connect=settings.ORCHESTRATOR_TIMEOUT_SECONDS,
            read=settings.ORCHESTRATOR_TIMEOUT_SECONDS,
            write=settings.ORCHESTRATOR_TIMEOUT_SECONDS,
        )
        async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload)
            except httpx.ReadTimeout:
                # (optional) log nicely or map to 504
                # e.g. raise HTTPException(status_code=504, detail="Orchestrator timed out")
                raise
            resp.raise_for_status()
            return resp.json()

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

