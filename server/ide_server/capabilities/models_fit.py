from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.models.fit import ModelFit, FitInfo


def _to_payload(fi: FitInfo) -> dict:
    return {
        "level": fi.level, "fitLabel": fi.fit_label,
        "memoryRequiredGb": fi.memory_required_gb, "memoryAvailableGb": fi.memory_available_gb,
        "estimatedTps": fi.estimated_tps, "diskSizeGb": fi.disk_size_gb,
        "bestQuant": fi.best_quant, "contextLength": fi.context_length,
        "score": fi.score, "scoreComponents": fi.score_components,
    }


def register(registry: Registry, root: Path, fit=None) -> None:
    fit = fit or ModelFit()

    async def models_fit(payload: dict) -> dict:
        repo_ids = list(payload.get("repoIds") or [])
        result = await fit.fit_for(repo_ids)
        return {r: (_to_payload(v) if v is not None else None) for r, v in result.items()}

    registry.register("models.fit", models_fit)
