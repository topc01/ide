from __future__ import annotations
import tomllib
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
    mlx = data.get("mlx")
    if not isinstance(mlx, dict) or not mlx.get("enabled") or not mlx.get("model"):
        return None
    return MlxConfig(
        model=str(mlx["model"]),
        router_prompt=str(mlx.get("router_prompt") or DEFAULT_ROUTER_PROMPT),
        port=int(mlx["port"]) if mlx.get("port") is not None else None,
    )
