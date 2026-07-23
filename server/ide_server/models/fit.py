from __future__ import annotations
import asyncio
import json
import subprocess
from dataclasses import dataclass


@dataclass
class FitInfo:
    repo_id: str
    level: str            # "ok" | "tight" | "no"
    fit_label: str
    memory_required_gb: float
    memory_available_gb: float
    estimated_tps: float
    disk_size_gb: float
    best_quant: str
    context_length: int
    score: float
    score_components: dict


def level_from(required: float, available: float) -> str:
    if not available or available <= 0:
        return "no"
    ratio = required / available
    if ratio <= 0.75:
        return "ok"
    if ratio <= 1.0:
        return "tight"
    return "no"


def _run_llmfit(repo_id: str) -> dict | None:
    try:
        proc = subprocess.run(["llmfit", "info", repo_id, "--json"],
                              capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not models:
        return None
    return models[0]


def _to_fit(repo_id: str, raw: dict) -> FitInfo:
    req = float(raw.get("memory_required_gb") or 0)
    avail = float(raw.get("memory_available_gb") or 0)
    comps = raw.get("score_components") or {}
    return FitInfo(
        repo_id=repo_id, level=level_from(req, avail), fit_label=str(raw.get("fit_label") or ""),
        memory_required_gb=req, memory_available_gb=avail,
        estimated_tps=float(raw.get("estimated_tps") or 0),
        disk_size_gb=float(raw.get("disk_size_gb") or 0),
        best_quant=str(raw.get("best_quant") or ""),
        context_length=int(raw.get("context_length") or 0),
        score=float(raw.get("score") or 0),
        score_components={k: comps.get(k) for k in ("fit", "speed", "quality", "context")},
    )


class ModelFit:
    def __init__(self, run=_run_llmfit) -> None:
        self._run = run
        self._cache: dict[str, FitInfo | None] = {}

    async def fit_for(self, repo_ids: list[str]) -> dict[str, FitInfo | None]:
        todo = [r for r in repo_ids if r not in self._cache]
        raws = await asyncio.gather(*(asyncio.to_thread(self._run, r) for r in todo))
        for repo_id, raw in zip(todo, raws):
            self._cache[repo_id] = _to_fit(repo_id, raw) if raw else None
        return {r: self._cache.get(r) for r in repo_ids}
