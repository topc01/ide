from ide_server.launcher import NullLauncher


def test_null_launcher_records_intent_without_spawning():
    launcher = NullLauncher()
    launcher.launch({"id": "s1", "name": "A"}, None)
    assert launcher.launched == [{"id": "s1", "name": "A"}]
