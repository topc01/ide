from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.mlx.config import mlx_config_raw, write_mlx_config


def register(registry: Registry, root: Path) -> None:
    async def get(_payload: dict) -> dict:
        r = mlx_config_raw(root)
        return {"enabled": r["enabled"], "model": r["model"],
                "routerPrompt": r["router_prompt"], "defaultPrompt": r["default_prompt"]}

    async def set_(payload: dict) -> dict:
        enabled = bool(payload.get("enabled"))
        model = (payload.get("model") or "").strip()
        router_prompt = payload.get("routerPrompt") or ""
        if enabled and not model:
            raise ValueError("elige un modelo para prender mlx")
        write_mlx_config(root, enabled=enabled, model=model, router_prompt=router_prompt)
        return {"saved": True}

    registry.register("mlx.config.get", get)
    registry.register("mlx.config.set", set_)
