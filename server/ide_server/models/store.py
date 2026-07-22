from __future__ import annotations
from dataclasses import dataclass


@dataclass
class InstalledModel:
    repo_id: str
    size_on_disk: int


def _scan_cache():
    from huggingface_hub import scan_cache_dir
    return scan_cache_dir()


def installed_models(scan=None) -> list[InstalledModel]:
    scan = scan or _scan_cache
    try:
        info = scan()
    except Exception:                                   # noqa: BLE001 — cache ausente = inventario vacío
        return []
    out: list[InstalledModel] = []
    for repo in info.repos:
        if getattr(repo, "repo_type", "model") == "model":
            out.append(InstalledModel(repo_id=repo.repo_id, size_on_disk=int(repo.size_on_disk)))
    return out


def delete_model(repo_id: str, scan=None) -> None:
    scan = scan or _scan_cache
    info = scan()
    hashes: list[str] = []
    for repo in info.repos:
        if repo.repo_id == repo_id:
            hashes.extend(rev.commit_hash for rev in repo.revisions)
    if not hashes:
        return
    info.delete_revisions(*hashes).execute()
