# server/ide_server/telegram.py
"""Puente Telegram ↔ sesión manager.

- El token del bot vive en el llavero de macOS (servicio `ide-telegram`, `ide telegram setup`).
- El chat se vincula una vez: `ide telegram setup` deja un código; mandarle `/start <código>` al bot
  guarda ese chat. Mensajes de cualquier otro chat se ignoran.
- Los mensajes del usuario se le encolan a la principal (`[Mensaje de Telegram del usuario]`); ella
  contesta con `ide reply` (solo a ese chat).
- Acciones remotas: `ide session propose <id|#n>` manda al chat la propuesta con botones Sí/No; el IDE
  la ejecuta (encola a esa sesión) solo con el Sí que llega de ese chat. La confirmación la da el
  usuario en Telegram, no la sesión: un texto malicioso no puede autoaprobarse.
Sin token o sin chat vinculado, el puente no hace nada. Long polling: nada expuesto a internet."""
from __future__ import annotations
import asyncio
import logging
import secrets
import subprocess
import sys
import time
from typing import Awaitable, Callable
import httpx
from ide_server.db import Db

log = logging.getLogger(__name__)
SERVICE = "ide-telegram"
API = "https://api.telegram.org/bot{token}/{method}"
MAX = 4000                                      # Telegram corta en 4096


def get_token() -> str | None:
    if sys.platform != "darwin":
        return None
    out = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", "bot", "-w"],
                         capture_output=True, text=True)
    return out.stdout.strip() or None if out.returncode == 0 else None


def set_token(token: str) -> None:
    """Al llavero por stdin (`security -i`): como argumento quedaría a la vista en `ps`."""
    if any(c in token for c in "\"\\\n "):
        raise RuntimeError("token con caracteres inválidos")
    out = subprocess.run(["security", "-i"], input=f'add-generic-password -U -s {SERVICE} -a bot -w "{token}"\n',
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"no pude guardar el token en el llavero: {out.stderr.strip()}")


class TelegramBridge:
    def __init__(self, db: Db, *, deliver: Callable[[str], Awaitable[str]],
                 propose_ok: Callable[[str, str], Awaitable[str]]) -> None:
        self.db = db
        self._deliver = deliver                 # texto → a la principal
        self._propose_ok = propose_ok           # (sesión, texto) → encolar (tras el Sí)
        self._token: str | None = None

    # -- API de Telegram -------------------------------------------------------------------------
    async def _call(self, client: httpx.AsyncClient, method: str, **params) -> dict:
        r = await client.post(API.format(token=self._token, method=method), json=params, timeout=40)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram {method}: {data.get('description')}")
        return data["result"]

    async def send(self, text: str, buttons: list[list[dict]] | None = None) -> None:
        chat = self.db.get("telegram:chat")
        if not self._token or not chat:
            raise RuntimeError("Telegram no está conectado (ide telegram setup)")
        async with httpx.AsyncClient() as client:
            chunks = [text[i:i + MAX] for i in range(0, len(text), MAX)] or [""]
            for i, chunk in enumerate(chunks):
                params = {"chat_id": chat, "text": chunk}
                if buttons and i == len(chunks) - 1:
                    params["reply_markup"] = {"inline_keyboard": buttons}
                await self._call(client, "sendMessage", **params)

    # -- propuestas (Sí/No) ------------------------------------------------------------------------
    async def propose(self, sid: str, label: str, text: str) -> str:
        pid = secrets.token_hex(6)
        self.db.set(f"telegram:prop:{pid}", {"sid": sid, "text": text, "at": time.time()})
        await self.send(f"La manager quiere mandarle esto a {label}:\n\n{text}",
                        buttons=[[{"text": "Sí, mandar", "callback_data": f"ok:{pid}"},
                                  {"text": "No", "callback_data": f"no:{pid}"}]])
        return pid

    async def _callback(self, client: httpx.AsyncClient, cq: dict) -> None:
        chat = self.db.get("telegram:chat")
        msg_chat = ((cq.get("message") or {}).get("chat") or {}).get("id")
        if not chat or msg_chat != chat or (cq.get("from") or {}).get("id") != chat:
            return                              # solo tu chat (y tú) aprueba
        action, _, pid = (cq.get("data") or "").partition(":")
        prop = self.db.get(f"telegram:prop:{pid}")
        self.db.delete(f"telegram:prop:{pid}")
        if not prop or time.time() - prop.get("at", 0) > 86400:
            answer = "Esa propuesta ya no existe (o venció)."
        elif action == "ok":
            try:
                answer = await self._propose_ok(prop["sid"], prop["text"])
            except Exception as exc:  # noqa: BLE001
                answer = f"No se pudo: {exc}"
        else:
            answer = "Descartada."
        await self._call(client, "answerCallbackQuery", callback_query_id=cq["id"], text=answer[:190])
        await self._call(client, "sendMessage", chat_id=chat, text=answer)

    # -- entrada ------------------------------------------------------------------------------------
    async def _message(self, client: httpx.AsyncClient, m: dict) -> None:
        chat_id = (m.get("chat") or {}).get("id")
        text = (m.get("text") or "").strip()
        if not text or (m.get("chat") or {}).get("type") != "private":
            return
        pair = self.db.get("telegram:pair") or {}
        if text.startswith("/start"):
            code = text.partition(" ")[2].strip()
            if pair.get("code") and secrets.compare_digest(code, pair["code"]) and time.time() < pair.get("until", 0):
                self.db.set("telegram:chat", chat_id)
                self.db.delete("telegram:pair")
                await self._call(client, "sendMessage", chat_id=chat_id,
                                 text="Listo: este chat quedó conectado a la sesión manager del IDE.")
            return
        if chat_id != self.db.get("telegram:chat"):
            return                              # otro chat: ni respuesta
        try:
            how = await self._deliver(text)
        except Exception as exc:  # noqa: BLE001
            how = f"no pude pasárselo a la manager: {exc}"
        if not how.startswith("encolado"):
            await self._call(client, "sendMessage", chat_id=chat_id, text=f"({how})")

    async def run(self, stop: asyncio.Event) -> None:
        async with httpx.AsyncClient() as client:
            while not stop.is_set():
                self._token = await asyncio.to_thread(get_token)
                if not self._token:
                    try:
                        await asyncio.wait_for(stop.wait(), 60)
                    except asyncio.TimeoutError:
                        pass
                    continue
                try:
                    updates = await self._call(client, "getUpdates", offset=self.db.get("telegram:offset", 0),
                                               timeout=25, allowed_updates=["message", "callback_query"])
                    for u in updates:
                        self.db.set("telegram:offset", u["update_id"] + 1)
                        if "callback_query" in u:
                            await self._callback(client, u["callback_query"])
                        elif "message" in u:
                            await self._message(client, u["message"])
                except Exception as exc:  # noqa: BLE001 — red caída, token malo: reintentar
                    # los errores de httpx traen la URL, que lleva el token: nunca al log
                    log.warning("telegram: %s", str(exc).replace(self._token or "\0", "<token>"))
                    try:
                        await asyncio.wait_for(stop.wait(), 15)
                    except asyncio.TimeoutError:
                        pass
