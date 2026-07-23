from __future__ import annotations
import tomllib
from typing import Any
import tomli_w
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROUTER_PROMPT = (
    "Sos un router de tareas. Si el mensaje del usuario es una pregunta simple, conceptual o de "
    "conversación que podés responder con confianza sin leer ni editar código, sin correr comandos "
    "y sin trabajar con el proyecto, RESPONDELO directamente. Si en cambio requiere leer/editar "
    "código, correr comandos, o trabajar con los archivos del proyecto, respondé EXACTAMENTE con "
    "esta única palabra y nada más: ROUTE_TO_CLAUDE"
)


@dataclass
class MlxConfig:
    model: str
    router_prompt: str
    port: int | None


def mlx_config(root: Path) -> MlxConfig | None:
    path = root / ".ide" / "config.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    mlx: dict[str, Any] | None = data.get("mlx")
    if not isinstance(mlx, dict) or not mlx.get("enabled") or not mlx.get("model"):
        return None
    return MlxConfig(
        model=str(mlx["model"]),
        router_prompt=str(mlx.get("router_prompt") or DEFAULT_ROUTER_PROMPT),
        port=int(mlx["port"]) if mlx.get("port") is not None else None,
    )


def mlx_config_raw(root: Path) -> dict[str, str | bool]:
    path = root / ".ide" / "config.toml"
    mlx: dict[str, Any] = {}
    if path.is_file():
        try:
            mlx = tomllib.loads(path.read_text(encoding="utf-8")).get("mlx") or {}
        except (tomllib.TOMLDecodeError, OSError):
            mlx = {}
    return {
        "enabled": bool(mlx.get("enabled")),
        "model": str(mlx.get("model") or ""),
        "router_prompt": str(mlx.get("router_prompt") or DEFAULT_ROUTER_PROMPT),
        "default_prompt": DEFAULT_ROUTER_PROMPT,
    }


def write_mlx_config(root: Path, *, enabled: bool, model: str, router_prompt: str) -> None:
    path = root / ".ide" / "config.toml"
    data: dict[str, Any] = {}
    if path.is_file():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    mlx: dict[str, str | bool] = data.setdefault("mlx", {})
    mlx["enabled"] = bool(enabled)
    if model:
        mlx["model"] = model
    else:
        mlx.pop("model", None)
    if router_prompt and router_prompt != DEFAULT_ROUTER_PROMPT:
        mlx["router_prompt"] = router_prompt
    else:
        mlx.pop("router_prompt", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(data), encoding="utf-8")
