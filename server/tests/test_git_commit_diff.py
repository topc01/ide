import subprocess
from pathlib import Path
from ide_server.git import file_diff_at_commit


def _repo(tmp_path: Path) -> tuple[Path, str]:
    r = tmp_path / "repo"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    (r / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "c1"], cwd=r, check=True)
    (r / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "c2"], cwd=r, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r,
                         capture_output=True, text=True).stdout.strip()
    return r, sha


def test_file_diff_at_commit_shows_that_commit_change(tmp_path):
    r, sha = _repo(tmp_path)
    lines = file_diff_at_commit(r, sha, "a.py")
    assert any(l["type"] == "add" and l["text"] == "dos" for l in lines)
    # el commit c2 no tocó la línea 'uno' salvo como contexto (no como add/del)
    assert not any(l["type"] == "del" for l in lines)
