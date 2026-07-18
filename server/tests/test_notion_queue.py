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


@pytest.mark.asyncio
async def test_max_retries_exhaustion():
    """Test that RateLimitedRunner raises RateLimited after exhausting max_retries.

    Guards against hanging by raising AssertionError if attempts exceed 50.
    """
    calls = {"n": 0}

    async def fake_sleep(s):
        pass

    runner = RateLimitedRunner(
        rate_per_sec=1000.0, sleep=fake_sleep, now=lambda: 0.0, max_retries=3
    )

    async def op():
        calls["n"] += 1
        # Guard against hanging: if we keep retrying, fail loudly
        if calls["n"] > 50:
            raise AssertionError(f"Op called {calls['n']} times, likely infinite loop")
        # Always raise RateLimited
        raise RateLimited(retry_after=0)

    # Should raise RateLimited after exhausting max_retries
    # Initial attempt + 3 retries = 4 total attempts
    with pytest.raises(RateLimited):
        await runner.run(op)

    # Assert exactly max_retries + 1 attempts (initial + retries)
    assert calls["n"] == 4
