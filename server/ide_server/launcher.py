from __future__ import annotations
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ide_server.roles import Role


class SessionLauncher(Protocol):
    def launch(self, session: dict, role: "Role | None") -> None: ...


class NullLauncher:
    """Launcher por defecto de R1: registra la intención, no spawnea Claude Code.

    El spawn real (binario `claude` por PTY) llega en R2 (Terminal). Los tests
    inyectan este launcher para no lanzar procesos.
    """

    def __init__(self) -> None:
        self.launched: list[dict] = []

    def launch(self, session: dict, role: "Role | None") -> None:
        self.launched.append(session)
