import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import tasks as tasks_cap


def _reg(tmp_path):
    (tmp_path / ".ide" / "tasks").mkdir(parents=True)
    reg = Registry()
    tasks_cap.register(reg, tmp_path)
    return reg


@pytest.mark.asyncio
async def test_create_list_read_save(tmp_path):
    reg = _reg(tmp_path)
    created = await reg.dispatch("tasks.create", {"name": "Alpha"})
    tid = created["task"]["id"]
    assert tid == "alpha"

    listed = await reg.dispatch("tasks.list", {})
    assert listed["tasks"] == [{"id": "alpha", "title": "Alpha", "status": "todo"}]

    read = await reg.dispatch("tasks.read", {"id": tid})
    assert read["markdown"] == "# Alpha\nstatus: todo\n"

    saved = await reg.dispatch("tasks.save", {"id": tid, "markdown": "# Alpha\nstatus: done\n"})
    assert saved == {"id": "alpha", "title": "Alpha", "status": "done"}


@pytest.mark.asyncio
async def test_read_id_invalido_propaga(tmp_path):
    reg = _reg(tmp_path)
    with pytest.raises(Exception):
        await reg.dispatch("tasks.read", {"id": "../secret"})
