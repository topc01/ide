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
