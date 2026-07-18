from pathlib import Path
from ide_server.git import (
    parse_numstat, parse_porcelain, merge_changes, parse_diff, untracked_lines,
)


def test_parse_numstat_counts_and_binary():
    raw = "3\t1\tsrc/a.py\n-\t-\timg.png\n"
    assert parse_numstat(raw) == [
        {"path": "src/a.py", "added": 3, "removed": 1},
        {"path": "img.png", "added": None, "removed": None},
    ]


def test_parse_porcelain_status_and_rename():
    raw = " M src/a.py\n?? new.txt\nR  old.py -> newp.py\n"
    assert parse_porcelain(raw) == [
        {"path": "src/a.py", "status": "M"},
        {"path": "new.txt", "status": "?"},
        {"path": "newp.py", "status": "R"},
    ]


def test_merge_changes_joins_by_path():
    porcelain = [{"path": "a.py", "status": "M"}, {"path": "new.txt", "status": "?"}]
    numstat = [{"path": "a.py", "added": 3, "removed": 1}]
    merged = {m["path"]: m for m in merge_changes(porcelain, numstat)}
    assert merged["a.py"] == {"path": "a.py", "status": "M", "added": 3, "removed": 1}
    assert merged["new.txt"] == {"path": "new.txt", "status": "?", "added": 0, "removed": 0}


def test_parse_diff_types_and_trailing_ctx():
    raw = (
        "diff --git a/x b/x\nindex 111..222 100644\n--- a/x\n+++ b/x\n"
        "@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
    )
    assert parse_diff(raw) == [
        {"type": "hunk", "text": "@@ -1,2 +1,2 @@"},
        {"type": "ctx", "text": "ctx"},
        {"type": "del", "text": "old"},
        {"type": "add", "text": "new"},
    ]


def test_untracked_lines_text_binary_missing(tmp_path):
    f = tmp_path / "t.txt"; f.write_text("a\nb\nc")           # sin newline final
    assert untracked_lines(f) == 3
    b = tmp_path / "b.bin"; b.write_bytes(b"\x00\x01\x02")
    assert untracked_lines(b) == 0
    assert untracked_lines(tmp_path / "nope") == 0
