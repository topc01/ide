import json, subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from ide_server.app import create_app
from ide_server.sessions_fs import seed_workspace


def _ws(tmp_path: Path) -> Path:
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True)
    seed_workspace(tmp_path)
    return tmp_path


def test_api_sessions_tree_empty(tmp_path):
    c = TestClient(create_app(_ws(tmp_path), claude_command="sleep 30"))
    body = c.get("/api/sessions").json()
    assert body["sessions"] == [] and body["workspaceRepos"][0]["id"] == "repoA"


def test_api_new_conflict_is_409(tmp_path):
    with TestClient(create_app(_ws(tmp_path), claude_command="sleep 30")) as c:
        assert c.post("/api/sessions", json={"id": "a", "prompt": ""}).status_code == 200
        r = c.post("/api/sessions", json={"id": "a", "prompt": ""})
        assert r.status_code == 409 and r.json()["code"] == "session_exists"
        assert c.post("/api/sessions/a/stop").status_code == 200


def test_ws_session_error_envelope(tmp_path):
    c = TestClient(create_app(_ws(tmp_path), claude_command="sleep 30"))
    with c.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "req", "id": "1", "channel": "sessions.open",
                                 "payload": {"id": "nope"}}))
        out = json.loads(ws.receive_text())
        assert out["type"] == "error" and out["payload"]["code"] == "unknown_session"


def test_http_missing_field_is_400(tmp_path, monkeypatch):
    from ide_server.capabilities import folder_sessions

    def boom(root, req):
        raise KeyError("id")

    monkeypatch.setattr(folder_sessions, "create_session", boom)
    with TestClient(create_app(_ws(tmp_path), claude_command="sleep 30")) as c:
        r = c.post("/api/sessions", json={})
        assert r.status_code == 400 and r.json()["code"] == "bad_request"
