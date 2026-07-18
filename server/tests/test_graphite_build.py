from ide_server.graphite import build_stack, GraphiteError


def test_build_stack_orders_and_flags_current():
    rows = [
        {"name": "main", "parent": None, "parentRevision": None, "revision": "r0"},
        {"name": "feat-a", "parent": "main", "parentRevision": "r0", "revision": "r1"},
        {"name": "feat-b", "parent": "feat-a", "parentRevision": "r1", "revision": "r2"},
    ]
    stack = build_stack(rows, current="feat-a")
    assert [b["name"] for b in stack] == ["main", "feat-a", "feat-b"]
    trunk = stack[0]
    assert trunk["isTrunk"] is True and trunk["needsRestack"] is False
    assert stack[1]["current"] is True and stack[2]["current"] is False
    # todas al día: parentRevision coincide con la revision del padre
    assert all(b["needsRestack"] is False for b in stack)


def test_build_stack_detects_needs_restack():
    # feat-a fue apilada sobre r0 pero main ahora está en rX → desactualizada
    rows = [
        {"name": "main", "parent": None, "parentRevision": None, "revision": "rX"},
        {"name": "feat-a", "parent": "main", "parentRevision": "r0", "revision": "r1"},
    ]
    stack = build_stack(rows, current=None)
    a = next(b for b in stack if b["name"] == "feat-a")
    assert a["needsRestack"] is True


def test_build_stack_no_trunk_raises():
    rows = [{"name": "orphan", "parent": "ghost", "parentRevision": "r", "revision": "r1"}]
    try:
        build_stack(rows, current=None)
        assert False, "esperaba GraphiteError"
    except GraphiteError:
        pass
