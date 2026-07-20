import pytest
from ide_server.tasks import store


def _dir(tmp_path):
    d = tmp_path / ".ide" / "tasks"
    d.mkdir(parents=True)
    return d


def test_list_tasks_titulo_status_y_fallback(tmp_path):
    d = _dir(tmp_path)
    (d / "a.md").write_text("# Alpha\nstatus: doing\n")
    (d / "b.md").write_text("sin titulo\n")
    tasks = store.list_tasks(tmp_path)
    assert tasks == [
        {"id": "a", "title": "Alpha", "status": "doing"},
        {"id": "b", "title": "b", "status": None},
    ]


def test_read_task(tmp_path):
    d = _dir(tmp_path)
    (d / "a.md").write_text("# Alpha\nstatus: todo\ncuerpo")
    t = store.read_task(tmp_path, "a")
    assert t == {"id": "a", "title": "Alpha", "status": "todo", "markdown": "# Alpha\nstatus: todo\ncuerpo"}


def test_read_task_inexistente(tmp_path):
    _dir(tmp_path)
    with pytest.raises(KeyError):
        store.read_task(tmp_path, "nope")


def test_write_task_persiste_y_devuelve_meta(tmp_path):
    d = _dir(tmp_path)
    (d / "a.md").write_text("# Viejo\n")
    meta = store.write_task(tmp_path, "a", "# Nuevo\nstatus: done\n")
    assert meta == {"id": "a", "title": "Nuevo", "status": "done"}
    assert (d / "a.md").read_text() == "# Nuevo\nstatus: done\n"


def test_create_task_slug_y_template(tmp_path):
    _dir(tmp_path)
    ref = store.create_task(tmp_path, "Mi Nueva Tarea")
    assert ref == {"id": "mi-nueva-tarea", "title": "Mi Nueva Tarea", "status": "todo"}
    assert (tmp_path / ".ide" / "tasks" / "mi-nueva-tarea.md").read_text() == "# Mi Nueva Tarea\nstatus: todo\n"


def test_create_task_colision_sufijo(tmp_path):
    _dir(tmp_path)
    store.create_task(tmp_path, "Dup")
    ref2 = store.create_task(tmp_path, "Dup")
    assert ref2["id"] == "dup-2"


def test_create_task_dir_inexistente_se_crea(tmp_path):
    # sin _dir(): create debe crear .ide/tasks
    ref = store.create_task(tmp_path, "X")
    assert (tmp_path / ".ide" / "tasks" / f"{ref['id']}.md").is_file()


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".."])
def test_task_id_invalido(tmp_path, bad):
    _dir(tmp_path)
    with pytest.raises(store.InvalidTaskId):
        store.read_task(tmp_path, bad)
