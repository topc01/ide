from __future__ import annotations


async def _httpx_post(url: str, json: dict) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=120.0) as cl:
        r = await cl.post(url, json=json)
        r.raise_for_status()
        return r.json()


class MlxClient:
    def __init__(self, base_url: str, *, model: str | None = None, http_post=None) -> None:
        self._base = base_url.rstrip("/")
        self._model = model
        self._post = http_post or _httpx_post

    async def chat(self, messages: list[dict]) -> str:
        # el `model` debe ser el id real cargado por el server; mlx_lm.server trata este campo
        # como un repo_id de HF y trataría de descargar uno llamado "local". Si es None, se omite
        # (mlx_lm.server usa el modelo cargado por default).
        body: dict = {"messages": messages}
        if self._model:
            body["model"] = self._model
        data = await self._post(f"{self._base}/v1/chat/completions", body)
        return data["choices"][0]["message"]["content"]
