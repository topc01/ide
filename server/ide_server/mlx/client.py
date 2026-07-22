from __future__ import annotations


async def _httpx_post(url: str, json: dict) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=120.0) as cl:
        r = await cl.post(url, json=json)
        r.raise_for_status()
        return r.json()


class MlxClient:
    def __init__(self, base_url: str, *, http_post=None) -> None:
        self._base = base_url.rstrip("/")
        self._post = http_post or _httpx_post

    async def chat(self, messages: list[dict]) -> str:
        data = await self._post(f"{self._base}/v1/chat/completions",
                                {"model": "local", "messages": messages})
        return data["choices"][0]["message"]["content"]
