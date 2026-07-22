from __future__ import annotations
import asyncio
import subprocess
import sys


class MlxUnavailable(RuntimeError):
    pass


async def _httpx_get_ok(url: str) -> bool:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as cl:
            return (await cl.get(url)).status_code == 200
    except Exception:                                  # noqa: BLE001
        return False


def _spawn(cmd: list[str]):
    return subprocess.Popen(cmd)


class MlxServer:
    def __init__(self, model: str, *, spawn=None, http_get=None, find_port=None,
                 host: str = "127.0.0.1", tries: int = 60, sleep=asyncio.sleep) -> None:
        self._model = model
        self._spawn = spawn or _spawn
        self._get = http_get or _httpx_get_ok
        self._host = host
        self._tries = tries
        self._sleep = sleep
        if find_port is None:
            from ide_server.cli import find_free_port
            find_port = find_free_port
        self._find_port = find_port
        self._proc = None
        self._url: str | None = None
        self._lock = asyncio.Lock()

    async def ensure_running(self) -> str:
        if self._proc is not None and self._proc.poll() is None and self._url:
            return self._url
        async with self._lock:
            # re-check adentro del lock: dos chat.send concurrentes durante la carga
            # del modelo no deben spawnear dos mlx_lm.server (el primero quedaría huérfano)
            if self._proc is not None and self._proc.poll() is None and self._url:
                return self._url
            port = self._find_port(self._host, 9000)
            cmd = [sys.executable, "-m", "mlx_lm.server", "--model", self._model,
                   "--port", str(port), "--host", self._host]
            try:
                self._proc = self._spawn(cmd)
            except (FileNotFoundError, OSError) as e:
                raise MlxUnavailable(f"no se pudo lanzar mlx_lm.server (¿instalaste ide-server[mlx]?): {e}")
            url = f"http://{self._host}:{port}"
            for _ in range(self._tries):
                if await self._get(f"{url}/v1/models"):
                    self._url = url
                    return url
                await self._sleep(1.0)
            self.stop()
            raise MlxUnavailable("el modelo local no cargó a tiempo")

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except Exception:                          # noqa: BLE001
                pass
        self._proc = None
        self._url = None
