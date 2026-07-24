from __future__ import annotations
import tomllib
from typing import Any
import tomli_w
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROUTER_PROMPT = (
    "Sos un CLASIFICADOR de tareas. Tu ÚNICA función es decidir quién debe responder — NO resolver "
    "la tarea vos mismo.\n\n"
    "Reglas:\n"
    "- Si el mensaje pide leer, editar o escribir código; correr comandos o tests; o trabajar con los "
    "archivos del proyecto → respondé EXACTAMENTE con la palabra ROUTE_TO_CLAUDE y NADA más. No "
    "intentes hacer la tarea ni escribir código.\n"
    "- Si es una pregunta simple, conceptual, de conocimiento general o de conversación que podés "
    "contestar de memoria en 1-2 frases → contestala directo.\n\n"
    "Ejemplos:\n"
    "usuario: editá main.py y agregá una función  → ROUTE_TO_CLAUDE\n"
    "usuario: corré los tests  → ROUTE_TO_CLAUDE\n"
    "usuario: arreglá el bug en el login  → ROUTE_TO_CLAUDE\n"
    "usuario: ¿cuál es la capital de Francia?  → La capital de Francia es París.\n"
    "usuario: ¿qué es una lista en Python?  → Una lista es una colección ordenada y mutable de elementos."
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
