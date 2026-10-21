# server/ide_server/evidence.py
"""Evidencias: una guía de pasos de prueba (qué hacer en la plataforma y dónde sacar captura) que se
va llenando con capturas. La define la sesión (`ide evidencias set`) o el usuario en el módulo
Evidencias; cada captura queda en `attachments/` de la sesión (su claude la ve) y en su paso. Una
sesión puede tener varias corridas (p.ej. "PR" y "Ticket": se duplica). Se exporta a markdown (con las
capturas como imágenes) para un comentario de la PR (`gh pr comment --attach`) o para copiar.

Archivo: `.ide/sessions/<sid>/evidence/<run>.json` = {id, label, created, steps: [{id, title, detail,
shot (lleva captura), shots: [nombres en attachments/], done}]}."""
from __future__ import annotations
import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from ide_server.sessions_fs import SessionError, session_path, workspace_lock

MAX_STEPS = 100
_SHOT_RE = re.compile(r"\s*(?:📸|\[captura\])\s*", re.I)
_ITEM_RE = re.compile(r"^\s{0,3}(?:\d+[.)]|[-*])\s+(?:\[[ xX]\]\s+)?(.*)$")


def _dir(root: Path, sid: str) -> Path:
    return session_path(root, sid) / "evidence"


def _sid_ok(run_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{1,80}", run_id or ""):
        raise SessionError("bad_request", f"corrida inválida: {run_id!r}")
    return run_id


def parse_steps(md: str) -> list[dict]:
    """Markdown → pasos: cada ítem de lista (`1.`, `-`, `- [ ]`) es un paso; las líneas que siguen
    (indentadas o no, hasta el próximo ítem) son su detalle. `📸` o `[captura]` = lleva captura."""
    steps: list[dict] = []
    for line in md.splitlines():
        m = _ITEM_RE.match(line)
        if m:
            text = m.group(1).strip()
            steps.append({"title": _SHOT_RE.sub(" ", text).strip(), "detail": "", "shot": bool(_SHOT_RE.search(text))})
        elif steps and line.strip():
            d = line.strip()
            if _SHOT_RE.search(d):
                steps[-1]["shot"] = True
                d = _SHOT_RE.sub(" ", d).strip()
            steps[-1]["detail"] = (steps[-1]["detail"] + "\n" + d).strip()
    return [_step(s) for s in steps if s["title"]][:MAX_STEPS]


def _step(s: dict) -> dict:
    return {"id": str(s.get("id") or secrets.token_hex(4)), "title": str(s.get("title") or "").strip()[:500],
            "detail": str(s.get("detail") or "").strip()[:4000], "shot": bool(s.get("shot", True)),
            "shots": [str(x) for x in s.get("shots") or [] if isinstance(x, str)], "done": bool(s.get("done"))}


def runs(root: Path, sid: str) -> list[dict]:
    d = _dir(root, sid)
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda r: r.get("created", ""))


def get(root: Path, sid: str, run_id: str) -> dict:
    f = _dir(root, sid) / f"{_sid_ok(run_id)}.json"
    if not f.is_file():
        raise SessionError("not_found", f"no existe la corrida {run_id}")
    return json.loads(f.read_text(encoding="utf-8"))


def save(root: Path, sid: str, run: dict) -> dict:
    """Guarda la corrida (pasos editados desde la UI): valida y normaliza."""
    run = {"id": _sid_ok(run["id"]), "label": str(run.get("label") or "Evidencias").strip()[:60],
           "created": run.get("created") or datetime.now().isoformat(timespec="seconds"),
           "steps": [_step(s) for s in (run.get("steps") or [])][:MAX_STEPS]}
    with workspace_lock(root):
        d = _dir(root, sid)
        d.mkdir(exist_ok=True)
        (d / f"{run['id']}.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return run


def new(root: Path, sid: str, label: str, steps: list[dict]) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:30] or "evidencias"
    return save(root, sid, {"id": f"{slug}-{datetime.now():%Y%m%d%H%M%S}", "label": label, "steps": steps})


def duplicate(root: Path, sid: str, run_id: str, label: str) -> dict:
    """Mismos pasos, sin capturas ni checks (p.ej. la segunda pasada, para el ticket)."""
    src = get(root, sid, run_id)
    return new(root, sid, label, [{**s, "id": None, "shots": [], "done": False} for s in src["steps"]])


def delete(root: Path, sid: str, run_id: str) -> None:
    (_dir(root, sid) / f"{_sid_ok(run_id)}.json").unlink(missing_ok=True)


def add_shot(root: Path, sid: str, run_id: str, step_id: str, name: str, raw: bytes) -> dict:
    """Guarda la captura en attachments/ y la suma al paso (que queda hecho)."""
    run = get(root, sid, run_id)
    i = next((i for i, s in enumerate(run["steps"]) if s["id"] == step_id), None)
    if i is None:
        raise SessionError("not_found", "no existe ese paso")
    ext = (Path(name).suffix.lower() or ".png")[:6]
    if not re.fullmatch(r"\.[a-z0-9]{1,5}", ext):
        ext = ".png"
    label = re.sub(r"[^a-z0-9]+", "-", run["label"].lower()).strip("-")[:20] or "evidencia"
    step = run["steps"][i]
    att = session_path(root, sid) / "attachments"
    att.mkdir(exist_ok=True)
    f = att / f"{datetime.now():%Y%m%d-%H%M%S}-evidencia-{label}-paso{i + 1}-{len(step['shots']) + 1}{ext}"
    f.write_bytes(raw)
    step["shots"].append(f.name)
    step["done"] = True
    return save(root, sid, run)


def markdown(root: Path, sid: str, run_id: str, *, images: bool = True) -> tuple[str, list[Path]]:
    """El markdown de la corrida y las capturas. `images`: como imágenes con su ruta absoluta (para
    `gh --attach`, que las reemplaza por las subidas); si no, el nombre de cada captura (para copiar:
    las imágenes se arrastran a mano)."""
    run = get(root, sid, run_id)
    att = session_path(root, sid) / "attachments"
    lines, files = [f"## Evidencias — {run['label']}", ""], []
    for n, s in enumerate(run["steps"], 1):
        lines.append(f"{n}. {'✅' if s['done'] else '⬜'} **{s['title']}**")
        if s["detail"]:
            lines += [f"   {d}" for d in s["detail"].splitlines()]
        for k, shot in enumerate(s["shots"], 1):
            f = att / shot
            if f.is_file():
                files.append(f)
                alt = f"Paso {n}{f' ({k})' if len(s['shots']) > 1 else ''}"
                lines += ["", f"   ![{alt}]({f})" if images else f"   _[captura: {shot}]_"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", files
