from ide_server.chat.permissions import resolve_permission

def test_override_skip_wins():
    assert resolve_permission({"read_only": True}, "skip") == ("bypassPermissions", None)

def test_override_normal_wins():
    assert resolve_permission({"skip": True}, "normal") == ("default", None)

def test_read_only_role_allows_reads():
    mode, tools = resolve_permission({"read_only": True}, None)
    assert mode == "default"
    assert tools == ["Read", "Grep", "Glob", "LS"]

def test_role_skip_default():
    assert resolve_permission({"skip": True}, None) == ("bypassPermissions", None)

def test_plain_role_is_normal():
    assert resolve_permission({}, None) == ("default", None)
    assert resolve_permission(None, None) == ("default", None)
