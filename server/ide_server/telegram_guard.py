# server/ide_server/telegram_guard.py
"""Protección del puente Telegram (si alguien se queda con tu Telegram, no puede hacer actuar a las sesiones).

- **Interruptor** (barra inferior del IDE, `kv telegram:on`; default encendido): apagado, el IDE ignora Telegram.
- **Mientras usas el IDE, Telegram está apagado**: la UI avisa cada vez que haces click o escribes en ella
  (`ui.presence`, solo por el websocket de la UI: un comando de una sesión no la puede fingir). Con actividad en los
  últimos `PRESENT` segundos, un mensaje por Telegram no le llega a la manager.
- **Código de verificación (2FA, TOTP de 6 dígitos)**: la clave se crea con `ide telegram 2fa` y vive en el llavero
  (servicio `ide-telegram`, cuenta `totp`) **con confirmación** (sin apps de confianza: leerla pregunta en la Mac); la
  cargas en una app de autenticación. El IDE nunca la lee: la tiene en memoria el guardián `totpd.py`, que no se
  reinicia con el IDE, y le pregunta si un código es correcto. Mandarle al bot el código del
  momento abre una **ventana** de `WINDOW` segundos: solo dentro de ella valen el «Sí» de una propuesta, un mensaje
  directo a Plugins y que la manager le mande trabajo directo a una sesión mientras no estás. `MAX_FAILS` códigos
  incorrectos bloquean `LOCK` segundos. Un código se acepta una sola vez."""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
import struct
import subprocess
import sys
import time

SERVICE = "ide-telegram"
PRESENT = 10 * 60          # «usando el IDE»: actividad en los últimos 10 min
WINDOW = 30 * 60           # la ventana que abre el código
MAX_FAILS = 5
LOCK = 60 * 60


# -- TOTP (RFC 6238, SHA1, 30 s, 6 dígitos) ---------------------------------------------------------------
def totp(secret_b32: str, at: float | None = None, step_offset: int = 0) -> tuple[int, str]:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    step = int((at if at is not None else time.time()) // 30) + step_offset
    h = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return step, f"{code:06d}"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def configured() -> bool:
    """¿Hay clave en el llavero? (solo los atributos: no la lee, no pregunta)."""
    if sys.platform != "darwin":
        return False
    return subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", "totp"],
                          capture_output=True, text=True).returncode == 0


def set_secret(secret: str) -> None:
    """Al llavero sin apps de confianza (`-T ""`): leerla pregunta en la Mac. Se borra la anterior (su ACL quedaría)."""
    if not secret.isalnum():
        raise RuntimeError("clave inválida")
    subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", "totp"], capture_output=True, text=True)
    out = subprocess.run(["security", "-i"], input=f'add-generic-password -s {SERVICE} -a totp -T "" -w "{secret}"\n',
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"no pude guardar la clave en el llavero: {out.stderr.strip()}")


def daemon_verify(code: str) -> dict | None:
    from ide_server import totpd
    return totpd.ask({"op": "verify", "code": code})


class Guard:
    def __init__(self, db, *, verify=daemon_verify, has_secret=configured, clock=time.time) -> None:
        self.db = db
        self._verify = verify
        self._has = has_secret
        self._clock = clock
        self._seen = 0.0                       # última actividad tuya en la UI (en memoria: un reinicio = ausente)

    # -- estado ---------------------------------------------------------------------------------------
    def touch(self) -> None:
        self._seen = self._clock()

    def present(self) -> bool:
        return self._clock() - self._seen < PRESENT

    def on(self) -> bool:
        return self.db.get("telegram:on", True) is not False

    def set_on(self, on: bool) -> None:
        self.db.set("telegram:on", bool(on))
        if not on:
            self.db.delete("telegram:window")

    def window_until(self) -> float:
        until = float(self.db.get("telegram:window") or 0)
        return until if until > self._clock() else 0.0

    def locked_until(self) -> float:
        lk = self.db.get("telegram:lock") or {}
        return float(lk.get("until") or 0) if float(lk.get("until") or 0) > self._clock() else 0.0

    def listening(self) -> bool:
        """¿Un mensaje de Telegram le llega a la manager ahora?"""
        return self.on() and not self.present()

    def can_act(self) -> bool:
        """¿Se puede hacer actuar a una sesión desde Telegram (o la manager, mientras no estás)?"""
        return self.window_until() > 0

    def manager_send_ok(self) -> bool:
        """La manager le manda trabajo directo a una sesión: sí si estás en el IDE o con Telegram apagado; mientras
        no estás y Telegram escucha, solo con la ventana abierta."""
        return not self.listening() or self.can_act()

    def status(self) -> dict:
        mode = ("off" if not self.on() else "ide" if self.present() else "window" if self.can_act() else "listening")
        return {"on": self.on(), "mode": mode, "windowUntil": self.window_until() or None,
                "lockedUntil": self.locked_until() or None, "twoFactor": self._has(),
                "presentFor": PRESENT, "window": WINDOW}

    # -- código ---------------------------------------------------------------------------------------
    def check_code(self, code: str) -> tuple[bool, str]:
        """(abrió la ventana, mensaje para Telegram)."""
        if self.locked_until():
            return False, "Demasiados códigos incorrectos: bloqueado hasta las " + time.strftime(
                "%H:%M", time.localtime(self.locked_until())) + "."
        if not self._has():
            return False, "No hay código configurado: en tu Mac, `ide telegram 2fa`."
        res = self._verify(code)
        if res is None:
            return False, ("El guardián del código no responde (¿se reinició la Mac? al arrancar, el llavero pide "
                           "«Permitir» en la Mac). Hasta entonces no puedo abrir la ventana.")
        now = self._clock()
        last = int(self.db.get("telegram:laststep") or 0)
        if res.get("ok") and int(res.get("step") or 0) > last:
            self.db.set("telegram:laststep", int(res["step"]))       # un código no se reusa
            self.db.delete("telegram:lock")
            self.db.set("telegram:window", now + WINDOW)
            return True, ("Código correcto: ventana abierta hasta las "
                          + time.strftime("%H:%M", time.localtime(now + WINDOW))
                          + ". Puedes aprobar propuestas y la manager puede mandarle trabajo a las sesiones.")
        lk = self.db.get("telegram:lock") or {}
        fails = int(lk.get("fails") or 0) + 1
        if fails >= MAX_FAILS:
            self.db.set("telegram:lock", {"fails": 0, "until": now + LOCK})
            return False, (f"Código incorrecto ({fails} seguidos): no acepto más códigos durante "
                           f"{LOCK // 60} minutos. Si no fuiste tú, apaga Telegram en el IDE y revisa tus sesiones de Telegram.")
        self.db.set("telegram:lock", {"fails": fails, "until": 0})
        return False, f"Código incorrecto ({fails} de {MAX_FAILS})."
