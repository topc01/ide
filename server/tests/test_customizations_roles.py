from pathlib import Path
from ide_server.customizations.readers import read_roles, roles_in_use


def _seed_sessions(root: Path, roles: list[str | None]):
    import json
    (root / ".ide").mkdir(parents=True, exist_ok=True)
    tree = [{"id": f"s{i}", "name": f"s{i}", "role": r, "children": []}
            for i, r in enumerate(roles)]
    (root / ".ide" / "sessions.json").write_text(json.dumps({"sessions": tree}))


def test_roles_in_use_reads_workspace_sessions(tmp_path):
    _seed_sessions(tmp_path, ["lector", "arquitecto", None])
    assert roles_in_use(tmp_path) == {"lector", "arquitecto"}


def test_read_roles_includes_presets_and_marks_in_use(tmp_path):
    _seed_sessions(tmp_path, ["arquitecto"])
    home = tmp_path / "home"           # sin ~/.ide/config.toml global
    rows = read_roles(home, tmp_path)
    labels = {r["label"] for r in rows}
    assert {"lector", "revisor", "arquitecto", "disenador"} <= labels   # PRESETS
    by = {r["label"]: r["inUse"] for r in rows}
    assert by["arquitecto"] is True and by["lector"] is False


def test_read_roles_merges_global_ide_config(tmp_path):
    _seed_sessions(tmp_path, [])
    home = tmp_path / "home"
    (home / ".ide").mkdir(parents=True)
    (home / ".ide" / "config.toml").write_text('[roles.mirole]\nmodel = "haiku"\n')
    labels = {r["label"] for r in read_roles(home, tmp_path)}
    assert "mirole" in labels
