import pytest
from ide_server.mlx.client import MlxClient


@pytest.mark.asyncio
async def test_chat_posts_openai_and_parses():
    captured = {}
    async def fake_post(url, json):
        captured["url"] = url; captured["json"] = json
        return {"choices": [{"message": {"content": "hola"}}]}
    c = MlxClient("http://localhost:9001", http_post=fake_post)
    out = await c.chat([{"role": "user", "content": "hi"}])
    assert out == "hola"
    assert captured["url"] == "http://localhost:9001/v1/chat/completions"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert "model" not in captured["json"]           # sin model configurado → se omite (no "local")


@pytest.mark.asyncio
async def test_chat_sends_configured_model_id():
    captured = {}
    async def fake_post(url, json):
        captured["json"] = json
        return {"choices": [{"message": {"content": "ok"}}]}
    c = MlxClient("http://x", model="mlx-community/Llama-3.2-1B-Instruct-4bit", http_post=fake_post)
    await c.chat([{"role": "user", "content": "hi"}])
    assert captured["json"]["model"] == "mlx-community/Llama-3.2-1B-Instruct-4bit"


@pytest.mark.asyncio
async def test_chat_stream_emits_chunks_and_returns_full():
    async def fake_stream(url, json):
        assert json["stream"] is True and json["model"] == "M"
        for c in ["ho", "la", "!"]:
            yield c
    got = []
    async def emit(c): got.append(c)
    client = MlxClient("http://x", model="M", http_stream=fake_stream)
    full = await client.chat_stream([{"role": "user", "content": "hi"}], emit)
    assert got == ["ho", "la", "!"] and full == "hola!"
