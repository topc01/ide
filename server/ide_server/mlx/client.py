from __future__ import annotations


async def _httpx_post(url: str, json: dict) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=120.0) as cl:
        r = await cl.post(url, json=json)
        r.raise_for_status()
        return r.json()


async def _httpx_stream(url: str, json: dict):
    # SSE OpenAI: líneas "data: {json}" con choices[0].delta.content; termina en "data: [DONE]"
    import json as _json
    import httpx
    async with httpx.AsyncClient(timeout=120.0) as cl:
        async with cl.stream("POST", url, json=json) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = _json.loads(data)
                    delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                except (ValueError, KeyError, IndexError, AttributeError):
                    continue
                if delta:
                    yield delta


class MlxClient:
    def __init__(self, base_url: str, *, model: str | None = None,
                 http_post=None, http_stream=None) -> None:
        self._base = base_url.rstrip("/")
        self._model = model
        self._post = http_post or _httpx_post
        self._stream = http_stream or _httpx_stream

    async def chat(self, messages: list[dict]) -> str:
        # el `model` debe ser el id real cargado por el server; mlx_lm.server trata este campo
        # como un repo_id de HF y trataría de descargar uno llamado "local". Si es None, se omite
        # (mlx_lm.server usa el modelo cargado por default).
        body: dict = {"messages": messages}
        if self._model:
            body["model"] = self._model
        data = await self._post(f"{self._base}/v1/chat/completions", body)
        return data["choices"][0]["message"]["content"]

    async def chat_stream(self, messages: list[dict], emit) -> str:
        # streamea la respuesta token a token: await emit(chunk) por cada delta. Devuelve el texto completo.
        body: dict = {"messages": messages, "stream": True}
        if self._model:
            body["model"] = self._model
        full: list[str] = []
        async for chunk in self._stream(f"{self._base}/v1/chat/completions", body):
            full.append(chunk)
            await emit(chunk)
        return "".join(full)
