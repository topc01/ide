from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedModel:
    repo_id: str
    label: str
    params: str
    quant: str
    size_gb: float


CURATED_MODELS: list[CuratedModel] = [
    CuratedModel("mlx-community/Llama-3.2-1B-Instruct-4bit", "Llama 3.2 1B Instruct", "1B", "4bit", 0.7),
    CuratedModel("mlx-community/Qwen2.5-3B-Instruct-4bit", "Qwen2.5 3B Instruct", "3B", "4bit", 1.7),
    CuratedModel("mlx-community/Llama-3.2-3B-Instruct-4bit", "Llama 3.2 3B Instruct", "3B", "4bit", 1.8),
    CuratedModel("mlx-community/Phi-3.5-mini-instruct-4bit", "Phi-3.5 mini Instruct", "3.8B", "4bit", 2.2),
    CuratedModel("mlx-community/Mistral-7B-Instruct-v0.3-4bit", "Mistral 7B Instruct v0.3", "7B", "4bit", 4.1),
    CuratedModel("mlx-community/Qwen2.5-7B-Instruct-4bit", "Qwen2.5 7B Instruct", "7B", "4bit", 4.3),
]
