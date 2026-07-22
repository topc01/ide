from __future__ import annotations
import asyncio


class DownloadState:
    def __init__(self) -> None:
        self.downloaded = 0
        self.total = 0


def _default_download(repo_id: str, state: "DownloadState") -> None:
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm as _tqdm

    class _Reporter(_tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.total:
                state.total += self.total

        def update(self, n=1):
            if n:
                state.downloaded += n
            return super().update(n)

    snapshot_download(repo_id, tqdm_class=_Reporter)


class ModelDownloader:
    def __init__(self, manager, *, download_fn=None, poll_interval: float = 0.5) -> None:
        self._manager = manager
        self._download = download_fn or _default_download
        self._poll = poll_interval
        self._active: dict[str, DownloadState] = {}

    async def start(self, repo_id: str):
        if repo_id in self._active:                      # dedup (event loop single-thread → sin lock)
            return None
        state = DownloadState()
        self._active[repo_id] = state
        return asyncio.create_task(self._run(repo_id, state))

    async def _run(self, repo_id: str, state: DownloadState) -> None:
        # el download bloqueante corre en un thread; el pump async emite progreso
        # leyendo el estado compartido (asignación de ints = GIL-safe).
        worker = asyncio.create_task(asyncio.to_thread(self._download, repo_id, state))
        try:
            while True:
                await self._manager.broadcast("models.event", {
                    "kind": "progress", "repoId": repo_id,
                    "downloaded": state.downloaded, "total": state.total})
                done, _ = await asyncio.wait({worker}, timeout=self._poll)
                if done:
                    break
            worker.result()                              # re-lanza si la descarga falló
            await self._manager.broadcast("models.event", {"kind": "done", "repoId": repo_id})
        except Exception as e:                           # noqa: BLE001 — todo error viaja como evento
            await self._manager.broadcast("models.event",
                {"kind": "error", "repoId": repo_id, "message": str(e)})
        finally:
            self._active.pop(repo_id, None)

    def active(self) -> dict:
        return {r: {"downloaded": s.downloaded, "total": s.total} for r, s in self._active.items()}
