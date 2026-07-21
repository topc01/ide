import json, os
from ide_server import instances


def test_register_and_list(tmp_path):
    p = instances.register_instance(tmp_path, port=8787, host="127.0.0.1",
                                    workspace="/ws/a", pid=os.getpid())
    assert p == tmp_path / ".ide" / "instances" / "8787.json"
    data = json.loads(p.read_text())
    assert data["port"] == 8787 and data["workspace"] == "/ws/a" and data["url"] == "http://127.0.0.1:8787"
    listed = instances.list_instances(tmp_path)
    assert len(listed) == 1 and listed[0]["port"] == 8787


def test_list_prunes_dead_pid(tmp_path):
    instances.register_instance(tmp_path, port=9001, host="127.0.0.1", workspace="/ws/x", pid=2147480000)
    assert instances.list_instances(tmp_path) == []                       # pid muerto → podado
    assert not (tmp_path / ".ide" / "instances" / "9001.json").exists()   # archivo borrado


def test_list_skips_corrupt_json(tmp_path):
    d = tmp_path / ".ide" / "instances"; d.mkdir(parents=True)
    (d / "8787.json").write_text("{ no es json")
    assert instances.list_instances(tmp_path) == []                       # no tumba el listado


def test_unregister(tmp_path):
    p = instances.register_instance(tmp_path, port=8787, host="127.0.0.1", workspace="/ws", pid=os.getpid())
    instances.unregister_instance(p)
    assert not p.exists()
    instances.unregister_instance(p)   # idempotente


def test_pid_alive():
    assert instances._pid_alive(os.getpid()) is True
    assert instances._pid_alive(2147480000) is False
