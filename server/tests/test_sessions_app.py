import json, subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from ide_server.app import create_app


def _ws(tmp_path: Path) -> Path:
    (tmp_path / ".ide" / "worktrees").mkdir(parents=True)
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True)
    return tmp_path


def test_api_sessions(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    assert c.get("/api/sessions").json() == {"sessions": [], "repos": [
        {"id": "repoA", "name": "repoA", "branch": "main"}]}


def test_ws_branch_occupied_error(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    with c.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "req", "id": "1", "channel": "sessions.create",
            "payload": {"name": "OnMain", "kind": "work", "repoId": "repoA",
                        "branch": "main", "access": "rw"}}))
        out = json.loads(ws.receive_text())
        assert out["type"] == "error"
        assert out["payload"]["code"] == "branch_occupied"
        assert out["payload"]["branch"] == "main"
