import asyncio, json
import pytest
from ide_server.pr_poller import PrPoller
from ide_server.sessions_fs import create_session_dir, update_session_toml


def _review(root, sid, url, sha):
    create_session_dir(root, sid=sid, kind="review", permissions="analyze", prompt="")
    update_session_toml(root, sid, lambda d: d.update(pr_url=url, reviewed_sha=sha))


def _gh(answers):
    async def run(args):
        url = args[2]
        a = answers[url]
        if isinstance(a, str):
            return 1, "", a
        return 0, json.dumps(a), ""
    return run


@pytest.mark.asyncio
async def test_poll_derives_states(tmp_path):
    _review(tmp_path, "r1", "u1", "aaa"); _review(tmp_path, "r2", "u2", "bbb")
    _review(tmp_path, "r3", "u3", "ccc")
    create_session_dir(tmp_path, sid="t", kind="ticket", permissions="analyze", prompt="")
    p = PrPoller(tmp_path, interval=60, clock=lambda: 0, run_gh=_gh({
        "u1": {"headRefOid": "aaa", "state": "OPEN"},
        "u2": {"headRefOid": "zzz", "state": "OPEN"},
        "u3": {"headRefOid": "ccc", "state": "MERGED"}}))
    assert await p.poll_once() is True
    assert p.derived["r1"]["prState"] is None
    assert p.derived["r2"]["prState"] == "stale"
    assert p.derived["r3"]["prState"] == "merged"
    assert "t" not in p.derived
    assert await p.poll_once() is False          # sin cambios → no notifica


@pytest.mark.asyncio
async def test_poll_error_keeps_last_state_marked_and_backs_off(tmp_path):
    _review(tmp_path, "r1", "u1", "aaa")
    answers = {"u1": {"headRefOid": "zzz", "state": "OPEN"}}
    p = PrPoller(tmp_path, interval=60, clock=lambda: 0, run_gh=_gh(answers))
    await p.poll_once()
    answers["u1"] = "HTTP 401: Bad credentials"
    await p.poll_once()
    d = p.derived["r1"]
    assert d["prState"] == "stale" and "401" in d["pollError"] and d["lastOk"]
    assert p.next_delay() == 120
    await p.poll_once()
    assert p.next_delay() == 240
    await p.poll_once()
    assert p.next_delay() == 240                  # tope 4× intervalo
    answers["u1"] = {"headRefOid": "zzz", "state": "OPEN"}
    await p.poll_once()
    assert p.next_delay() == 60 and p.derived["r1"]["pollError"] is None


@pytest.mark.asyncio
async def test_run_disabled_and_stops(tmp_path):
    p = PrPoller(tmp_path, interval=0, run_gh=_gh({}))
    await asyncio.wait_for(p.run(asyncio.Event()), 1)       # interval 0 → retorna ya
    stop = asyncio.Event(); calls = []
    _review(tmp_path, "r1", "u1", "aaa")
    p2 = PrPoller(tmp_path, interval=60, run_gh=_gh({
        "u1": {"headRefOid": "zzz", "state": "OPEN"}}), on_change=lambda: calls.append(1))
    task = asyncio.create_task(p2.run(stop))
    await asyncio.sleep(0.05); stop.set()
    await asyncio.wait_for(task, 1)
    assert calls == [1]


@pytest.mark.asyncio
async def test_invalid_gh_output_marks_error_and_poll_returns(tmp_path):
    _review(tmp_path, "r1", "u1", "aaa")
    async def bad_json(args):
        return 0, "not json", ""
    p = PrPoller(tmp_path, interval=60, clock=lambda: 0, run_gh=bad_json)
    assert await p.poll_once() is True           # el error aparece: cambio real, y no revienta
    assert "respuesta inválida de gh" in p.derived["r1"]["pollError"]

    async def non_dict(args):
        return 0, "[1]", ""
    p = PrPoller(tmp_path, interval=60, clock=lambda: 0, run_gh=non_dict)
    await p.poll_once()
    assert "respuesta inválida de gh" in p.derived["r1"]["pollError"]


@pytest.mark.asyncio
async def test_runner_exception_marks_error(tmp_path):
    _review(tmp_path, "r1", "u1", "aaa")
    async def boom(args):
        raise RuntimeError("boom")
    p = PrPoller(tmp_path, interval=60, clock=lambda: 0, run_gh=boom)
    await p.poll_once()
    assert "boom" in p.derived["r1"]["pollError"]


@pytest.mark.asyncio
async def test_run_survives_on_change_error(tmp_path):
    _review(tmp_path, "r1", "u1", "aaa")
    polls = []
    base = _gh({"u1": {"headRefOid": "zzz", "state": "OPEN"}})
    async def counting(args):
        polls.append(1)
        return await base(args)
    def boom():
        raise RuntimeError("cb")
    p = PrPoller(tmp_path, interval=60, run_gh=counting, on_change=boom)
    p.next_delay = lambda: 0.01
    stop = asyncio.Event()
    task = asyncio.create_task(p.run(stop))
    await asyncio.sleep(0.1); stop.set()
    await asyncio.wait_for(task, 1)           # no debe haber muerto con la excepción
    assert len(polls) > 1


@pytest.mark.asyncio
async def test_default_gh_timeout_kills_and_returns_124(tmp_path, monkeypatch):
    import os, time
    from ide_server import pr_poller
    fake = tmp_path / "bin"; fake.mkdir()
    gh = fake / "gh"
    gh.write_text("#!/bin/sh\nexec sleep 5\n")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(pr_poller, "GH_TIMEOUT", 0.2)
    t0 = time.monotonic()
    code, out, err = await pr_poller._default_gh(["pr", "view", "x"])
    assert code == 124 and "timeout" in err
    assert time.monotonic() - t0 < 3
