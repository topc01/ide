from __future__ import annotations
import tomllib
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.models.catalog import CURATED_MODELS
from ide_server.models.store import installed_models, delete_model


def _in_use(root: Path) -> str | None:
    path = root / ".ide" / "config.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    mlx = data.get("mlx")
    if isinstance(mlx, dict) and mlx.get("enabled") and mlx.get("model"):
        return str(mlx["model"])
    return None


def register(registry: Registry, root: Path, manager, downloader=None,
             installed=installed_models, remove=delete_model) -> None:
    async def list_(_payload: dict) -> dict:
        return {
            "curated": [{"repoId": m.repo_id, "label": m.label, "params": m.params,
                         "quant": m.quant, "sizeGb": m.size_gb} for m in CURATED_MODELS],
            "installed": [{"repoId": m.repo_id, "sizeOnDisk": m.size_on_disk} for m in installed()],
            "active": downloader.active() if downloader is not None else {},
            "inUse": _in_use(root),
        }

    async def download(payload: dict) -> dict:
        repo_id = (payload.get("repoId") or "").strip()
        if not repo_id:
            raise ValueError("repoId vacío")
        if downloader is not None:
            await downloader.start(repo_id)
        return {"started": True}

    async def delete(payload: dict) -> dict:
        repo_id = (payload.get("repoId") or "").strip()
        if repo_id:
            remove(repo_id)
        return {"deleted": True}

    for ch, fn in {"models.list": list_, "models.download": download,
                   "models.delete": delete}.items():
        registry.register(ch, fn)
