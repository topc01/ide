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
    p2 = PrPoller(tmp_path, interval=60, run_gh=_gh({}), on_change=lambda: calls.append(1))
    task = asyncio.create_task(p2.run(stop))
    await asyncio.sleep(0.05); stop.set()
    await asyncio.wait_for(task, 1)
