import base64, json, subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from ide_server.app import create_app


def _ws(tmp_path: Path) -> Path:
    (tmp_path / ".ide").mkdir()
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True)
    return tmp_path


def test_terminal_output_streams_as_event(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    with c.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "req", "id": "1", "channel": "terminal.open",
                                 "payload": {"repoId": "repoA", "cmd": ["echo", "streamed-hi"]}}))
        tid = None
        got = b""
        for _ in range(60):
            msg = json.loads(ws.receive_text())
            if msg["type"] == "res" and msg["id"] == "1":
                tid = msg["payload"]["id"]
            elif msg["type"] == "event" and msg["channel"] == f"terminal.data.{tid}":
                got += base64.b64decode(msg["payload"]["data"])
                if b"streamed-hi" in got:
                    break
        assert b"streamed-hi" in got
