import json, subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from ide_server.app import create_app

def _ws(tmp_path: Path):
    (tmp_path / ".ide").mkdir()
    r = tmp_path / "repo-a"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=r, check=True)
    return tmp_path

def test_health(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    assert c.get("/health").json()["status"] == "ok"

def test_api_repos(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    data = c.get("/api/repos").json()
    assert data["repos"][0]["name"] == "repo-a"

def test_ws_req_res(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    with c.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "req", "id": "1", "channel": "repos.list", "payload": {}}))
        out = json.loads(ws.receive_text())
        assert out["type"] == "res" and out["id"] == "1"

def test_serves_frontend_when_web_dir(tmp_path):
    ws = _ws(tmp_path)
    web = tmp_path / "web"; web.mkdir()
    (web / "index.html").write_text("<html>IDE</html>")
    c = TestClient(create_app(ws, web_dir=web))
    assert "<html>IDE</html>" in c.get("/").text        # sirve index
    assert c.get("/health").json()["status"] == "ok"    # ruta específica gana
    assert c.get("/api/repos").json()["repos"][0]["name"] == "repo-a"


def test_no_web_dir_still_ok(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))            # sin web_dir
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/").status_code == 404                # no monta estáticos
