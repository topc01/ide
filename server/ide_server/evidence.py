# server/ide_server/evidence.py
"""Evidencias: una guía de pasos de prueba (qué hacer en la plataforma y dónde sacar captura) que se
va llenando con capturas. La define la sesión (`ide evidence plan`) o el usuario en el módulo
Evidencias; cada captura queda en `attachments/` de la sesión (su claude la ve) y en su paso. Una
sesión puede tener varias corridas (p.ej. "PR" y "Ticket": se duplica). Se exporta a markdown (con las
capturas como imágenes) para un comentario de la PR (`gh pr comment --attach`) o para copiar.

Archivo: `.ide/sessions/<sid>/evidence/<run>.json` = {id, label, created, steps: [{id, title, detail,
shot (lleva captura), shots: [nombres en attachments/], done}]}."""
from __future__ import annotations
import json
import re
import secrets
import subprocess
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
            "shots": [x for x in s.get("shots") or [] if _bare(x)], "done": bool(s.get("done"))}


def _bare(name) -> bool:
    """Una captura es un nombre de archivo pelado de attachments/ (nunca una ruta: se sube a GitHub)."""
    return isinstance(name, str) and bool(re.fullmatch(r"[A-Za-z0-9._-]{1,200}", name)) \
        and Path(name).name == name and name not in (".", "..")


def runs(root: Path, sid: str) -> list[dict]:
    d = _dir(root, sid)
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
            out.append({**run, "steps": [_step(s) for s in run.get("steps") or []]})
        except (OSError, ValueError, AttributeError):
            continue
    return sorted(out, key=lambda r: r.get("created", ""))


def get(root: Path, sid: str, run_id: str) -> dict:
    f = _dir(root, sid) / f"{_sid_ok(run_id)}.json"
    if not f.is_file():
        raise SessionError("not_found", f"no existe la corrida {run_id}")
    run = json.loads(f.read_text(encoding="utf-8"))
    return {**run, "steps": [_step(s) for s in run.get("steps") or []]}   # el archivo se puede editar a mano


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
    ext = _media_ext(raw)
    if ext is None:                             # se sube a GitHub: solo imágenes y videos de verdad
        raise SessionError("bad_request", "la captura tiene que ser una imagen (png, jpg, gif, webp) o un video (mp4, mov)")
    label = re.sub(r"[^a-z0-9]+", "-", run["label"].lower()).strip("-")[:20] or "evidencia"
    step = run["steps"][i]
    att = session_path(root, sid) / "attachments"
    att.mkdir(exist_ok=True)
    f = att / f"{datetime.now():%Y%m%d-%H%M%S}-evidencia-{label}-paso{i + 1}-{len(step['shots']) + 1}{ext}"
    f.write_bytes(raw)
    step["shots"].append(f.name)
    step["done"] = True
    return save(root, sid, run)


def _media_ext(raw: bytes) -> str | None:
    """Extensión según el contenido (no el nombre)."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    if raw[4:8] == b"ftyp":
        return ".mov" if raw[8:10] == b"qt" else ".mp4"
    return None


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
            f = (att / shot).resolve()
            # el JSON se puede editar a mano: solo archivos reales dentro de attachments/
            if _bare(shot) and f.is_relative_to(att.resolve()) and f.is_file():
                files.append(f)
                alt = f"Paso {n}{f' ({k})' if len(s['shots']) > 1 else ''}"
                lines += ["", f"   ![{alt}]({f})" if images else f"   _[captura: {shot}]_"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", files


def _gh(args: list[str], text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], input=text, capture_output=True, text=True, timeout=300)


def publish(url: str, text: str, files: list[Path]) -> dict:
    """Publica la guía como comentario en la PR (`gh pr comment --attach`: sube cada captura y reemplaza su
    ruta en el texto) y **verifica** el comentario publicado: con gh 2.102 `pr comment` a veces deja sin
    subir la última referencia (queda la ruta local, imagen rota). Si quedó alguna, reintenta con
    `--edit-last` adjuntando solo esas (hasta 2 veces); si sigue faltando, falla. Devuelve {comment, attachments}."""
    from ide_server.session_ops import parse_pr_url
    attach = lambda fs: [x for f in fs for x in ("--attach", str(f))]   # noqa: E731 — una lista: nada de separar texto
    out = _gh(["pr", "comment", url, "--body-file", "-", *attach(files)], text)
    if out.returncode != 0:
        raise SessionError("gh_failed", f"gh pr comment: {out.stderr.strip() or out.returncode}")
    link = out.stdout.strip()
    m = re.search(r"#issuecomment-(\d+)", link)
    full = re.search(r"github\.com/([^/]+/[^/]+)/pull/\d+", url)
    if not m or not full:
        raise SessionError("gh_failed", f"no pude ubicar el comentario publicado ({link or 'sin link'}) para verificarlo")
    missing: list[Path] = []
    body = ""
    for attempt in range(3):
        got = _gh(["api", f"repos/{full.group(1)}/issues/comments/{m.group(1)}", "--jq", ".body"])
        if got.returncode != 0:
            raise SessionError("gh_failed", f"no pude leer el comentario publicado: {got.stderr.strip()}")
        body = got.stdout
        missing = [f for f in files if f"({f})" in body]
        if not missing or attempt == 2:
            break
        retry = _gh(["pr", "comment", url, "--edit-last", "--body-file", "-", *attach(missing)], body)
        if retry.returncode != 0:
            raise SessionError("gh_failed", f"gh pr comment --edit-last: {retry.stderr.strip() or retry.returncode}")
    if missing:
        raise SessionError("partial", f"el comentario quedó sin {len(missing)} captura(s) (imagen rota): "
                                      + ", ".join(f.name for f in missing) + f" — {link}")
    return {"comment": link, "attachments": body.count("user-attachments"), "shots": len(files)}
