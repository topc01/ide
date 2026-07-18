import pytest
from ide_server.notion.queue import RateLimitedRunner, RateLimited


@pytest.mark.asyncio
async def test_serializes_and_spaces(monkeypatch):
    clock = {"t": 0.0}
    slept = []

    async def fake_sleep(s):
        slept.append(s)
        clock["t"] += s

    runner = RateLimitedRunner(rate_per_sec=3.0, sleep=fake_sleep, now=lambda: clock["t"])
    order = []

    async def op(n):
        order.append(n)
        return n

    assert await runner.run(lambda: op(1)) == 1
    assert await runner.run(lambda: op(2)) == 2
    assert order == [1, 2]
    # el 2º despacho esperó ~1/3 s porque el reloj no avanzó solo
    assert any(abs(s - (1 / 3)) < 1e-6 for s in slept)


@pytest.mark.asyncio
async def test_retries_on_rate_limited():
    calls = {"n": 0}

    async def fake_sleep(s):
        pass

    runner = RateLimitedRunner(rate_per_sec=1000.0, sleep=fake_sleep, now=lambda: 0.0)

    async def op():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimited(retry_after=0.01)
        return "ok"

    assert await runner.run(op) == "ok"
    assert calls["n"] == 2
