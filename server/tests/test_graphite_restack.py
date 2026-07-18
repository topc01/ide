import shutil
import subprocess
from pathlib import Path
import pytest
from ide_server.graphite import restack, GraphiteError

pytestmark = pytest.mark.skipif(shutil.which("gt") is None, reason="gt no instalado")


def test_restack_on_non_graphite_repo_raises_and_cleans(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=r, check=True)
    # branch inexistente / repo no trackeado por gt → gt falla → GraphiteError
    with pytest.raises(GraphiteError):
        restack(r, "no-existe")
    # el repo no quedó a medio-rebase
    assert not (r / ".git" / "rebase-merge").exists()
    assert not (r / ".git" / "rebase-apply").exists()
