# Conectar Notion in-app Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configurar la conexión a Notion desde la app (pegar el token en el panel) en vez de editar `~/.ide/config.toml` a mano — validando el token antes de persistirlo.

**Architecture:** Extiende el módulo `notion/` y la capability `notion` (Fase 1, ya en main): `write_token`/`clear_token` en `notion/config.py` (con `tomli-w`), capability `notion.connect`/`notion.disconnect`, y una vista de conexión en `NotionPanel`.

**Tech Stack:** Backend Python (`uv`, `pytest`, `tomli-w`); frontend React + Vite + TS (Zustand, Vitest + Testing Library).

## Global Constraints

- **Sin fallos silenciosos:** token inválido → `{connected:false}` (el front muestra "token inválido"), NO se persiste; error de red/IO → envelope. Nunca guardar un token que no valida.
- **Validar antes de persistir:** `notion.connect` valida con `users.me` usando el token provisto; solo escribe si responde.
- **El token va al global** `~/.ide/config.toml [notion].token`, preservando otras secciones. Resolución existente (`notion_token`: env > local > global) sin cambios.
- **TDD estricto**, un commit por tarea, conventional commits en español.
- **Tests:** backend `cd server && uv run pytest -q`; frontend `cd ui && npm test`.

---

### Task 1: `write_token` / `clear_token` + dep `tomli-w`

**Files:**
- Modify: `server/ide_server/notion/config.py` (append)
- Modify: `server/pyproject.toml` (dep `tomli-w`)
- Test: `server/tests/test_notion_config.py` (append)

**Interfaces:**
- Produces: `write_token(home: Path, token: str) -> None` (escribe `[notion].token` en `home/.ide/config.toml`, preservando el resto, creando el dir si falta); `clear_token(home: Path) -> None` (quita el token; no-op si el archivo no existe).

- [ ] **Step 1: Add the dependency**

Run: `cd server && uv add "tomli-w>=1.0"`
Expected: `pyproject.toml` gains `tomli-w`, lock updated, `import tomli_w` resolvable.

- [ ] **Step 2: Write the failing test** (append a `server/tests/test_notion_config.py`)

```python
from ide_server.notion.config import write_token, clear_token, notion_token


def test_write_token_creates_and_preserves(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    home = tmp_path / "home"
    # sección previa que NO se debe pisar
    (home / ".ide").mkdir(parents=True)
    (home / ".ide" / "config.toml").write_text('name = "demo"\n')
    write_token(home, "secret-abc")
    import tomllib
    data = tomllib.loads((home / ".ide" / "config.toml").read_text())
    assert data["name"] == "demo"
    assert data["notion"]["token"] == "secret-abc"
    assert notion_token(home, tmp_path / "no-root") == "secret-abc"


def test_write_token_creates_dir_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    home = tmp_path / "fresh"
    write_token(home, "tok")
    assert notion_token(home, tmp_path / "no-root") == "tok"


def test_clear_token_removes_and_keeps_rest(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    home = tmp_path / "home"
    (home / ".ide").mkdir(parents=True)
    (home / ".ide" / "config.toml").write_text('name = "demo"\n[notion]\ntoken = "x"\n')
    clear_token(home)
    import tomllib
    data = tomllib.loads((home / ".ide" / "config.toml").read_text())
    assert data["name"] == "demo" and "notion" not in data
    assert notion_token(home, tmp_path / "no-root") is None


def test_clear_token_missing_file_noop(tmp_path):
    clear_token(tmp_path / "nope")   # no explota
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_config.py -q`
Expected: FAIL (`ImportError: cannot import name 'write_token'`)

- [ ] **Step 4: Write minimal implementation** (append a `server/ide_server/notion/config.py`; agrega `import tomli_w` arriba con los otros imports)

```python
def write_token(home: Path, token: str) -> None:
    cfg = home / ".ide" / "config.toml"
    data: dict = {}
    if cfg.is_file():
        try:
            data = tomllib.loads(cfg.read_text())
        except tomllib.TOMLDecodeError:
            data = {}
    data.setdefault("notion", {})["token"] = token
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(tomli_w.dumps(data))


def clear_token(home: Path) -> None:
    cfg = home / ".ide" / "config.toml"
    if not cfg.is_file():
        return
    try:
        data = tomllib.loads(cfg.read_text())
    except tomllib.TOMLDecodeError:
        return
    notion = data.get("notion")
    if isinstance(notion, dict):
        notion.pop("token", None)
        if not notion:
            data.pop("notion", None)
    cfg.write_text(tomli_w.dumps(data))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_config.py -q`
Expected: PASS (existing 3 + new 4)

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/notion/config.py server/pyproject.toml server/uv.lock server/tests/test_notion_config.py
git commit -m "feat(notion): write_token/clear_token en config global + dep tomli-w"
```

---

### Task 2: Capability `notion.connect` / `notion.disconnect`

**Files:**
- Modify: `server/ide_server/capabilities/notion.py`
- Test: `server/tests/test_notion_capability.py` (append)

**Interfaces:**
- Consumes: `config.write_token`/`clear_token` (Task 1), `make_client` (existente, inyectable).
- Produces: `notion.connect {token}` → valida con `users.me` (token provisto); OK → `write_token` → `{connected:true}`; inválido/vacío → `{connected:false}` sin persistir. `notion.disconnect {}` → `clear_token` → `{connected:false}`.

- [ ] **Step 1: Write the failing test** (append a `server/tests/test_notion_capability.py`)

El archivo ya tiene un `_FakeClient` con `users.me` (configurable para éxito/fallo) y el helper `_reg(tmp_path, token=...)` que registra con `client_factory` y `home`. Reutilízalos. Nota: `_reg` usa un `home` bajo `tmp_path`; `write_token`/`clear_token` operan sobre ese `home`.

```python
@pytest.mark.asyncio
async def test_connect_valid_token_persists(tmp_path):
    # sin token al inicio
    reg, fake = _reg(tmp_path, token="")
    assert (await reg.dispatch("notion.health", {}))["connected"] is False
    out = await reg.dispatch("notion.connect", {"token": "secret-xyz"})
    assert out["connected"] is True
    # persistió en el home global de _reg → health ahora true
    assert (await reg.dispatch("notion.health", {}))["connected"] is True


@pytest.mark.asyncio
async def test_connect_invalid_token_not_persisted(tmp_path):
    # client_factory cuyo users.me() falla
    class _Bad:
        class _U:
            async def me(self): raise RuntimeError("401")
        @property
        def users(self): return self._U()
    (tmp_path / ".ide").mkdir(exist_ok=True)
    home = tmp_path / "home2"; (home / ".ide").mkdir(parents=True)
    from ide_server.plugins import Registry
    from ide_server.capabilities import notion as notion_cap
    reg = Registry(); notion_cap.register(reg, tmp_path, home=home, client_factory=lambda t: _Bad())
    out = await reg.dispatch("notion.connect", {"token": "bad"})
    assert out["connected"] is False
    assert not (home / ".ide" / "config.toml").exists() or "token" not in (home / ".ide" / "config.toml").read_text()


@pytest.mark.asyncio
async def test_connect_empty_token(tmp_path):
    reg, _ = _reg(tmp_path, token="")
    assert (await reg.dispatch("notion.connect", {"token": ""}))["connected"] is False


@pytest.mark.asyncio
async def test_disconnect_clears(tmp_path):
    reg, _ = _reg(tmp_path, token="preset")   # _reg escribe el token global
    assert (await reg.dispatch("notion.health", {}))["connected"] is True
    await reg.dispatch("notion.disconnect", {})
    assert (await reg.dispatch("notion.health", {}))["connected"] is False
```

Nota: si el helper `_reg` escribe el token en un `config.toml` que `clear_token` debe poder limpiar, verifica que `_reg(token="preset")` cree ese archivo bajo el mismo `home` que la capability usa. Si `_reg` setea el token de otra forma (p.ej. solo en el archivo global), `test_disconnect_clears` valida el path real; ajusta el helper mínimamente si hace falta para que health lea del archivo que `clear_token` toca.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_capability.py -q`
Expected: FAIL (`unknown_channel: notion.connect` o similar)

- [ ] **Step 3: Write minimal implementation**

En `server/ide_server/capabilities/notion.py`: cambia el import de config para traer los writers —
`from ide_server.notion.config import notion_token, write_token, clear_token` — y agrega los handlers dentro de `register` (junto a los demás), luego regístralos:

```python
    async def connect(p: dict) -> dict:
        token = (p.get("token") or "").strip()
        if not token:
            return {"connected": False}
        try:
            await make_client(token).users.me()
        except Exception:                                  # noqa: BLE001 — token inválido/red
            return {"connected": False}
        write_token(home, token)
        return {"connected": True}

    async def disconnect(_p: dict) -> dict:
        clear_token(home)
        return {"connected": False}
```

Agrega `("connect", connect), ("disconnect", disconnect)` a la lista de registro de canales
`notion.*`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_capability.py tests/test_app.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/notion.py server/tests/test_notion_capability.py
git commit -m "feat(notion): capability connect (valida + persiste) / disconnect"
```

---

### Task 3: Transport + store `connect`/`disconnect`

**Files:**
- Modify: `ui/src/transport/notionChannel.ts`
- Modify: `ui/src/state/notion.ts`
- Test: `ui/src/transport/notionChannel.test.ts` (append)
- Test: `ui/src/state/notion.test.ts` (append)

**Interfaces:**
- Produces: `connect(ws, token) -> Promise<boolean>` (→ `.connected`), `disconnect(ws) -> Promise<void>`. Store `useNotion` gana `connect(token)` (OK → `load()`; inválido → `error:"token inválido"`) y `disconnect()` (→ `{connected:false, pages:[]}`).

- [ ] **Step 1: Write the failing test**

Append a `ui/src/transport/notionChannel.test.ts`:

```typescript
it("connect manda el token y devuelve connected", async () => {
  const ws = { request: vi.fn().mockResolvedValue({ connected: true }) } as any;
  expect(await connect(ws, "tok")).toBe(true);
  expect(ws.request).toHaveBeenCalledWith("notion.connect", { token: "tok" });
});
it("disconnect llama notion.disconnect", async () => {
  const ws = { request: vi.fn().mockResolvedValue({ connected: false }) } as any;
  await disconnect(ws);
  expect(ws.request).toHaveBeenCalledWith("notion.disconnect", {});
});
```

(agrega `connect, disconnect` al import de `./notionChannel` en ese test.)

Append a `ui/src/state/notion.test.ts` (mockea `connect`/`disconnect` en el `vi.mock` de notionChannel — agrega `connect: (...a)=>connectFn(...a)`, `disconnect: (...a)=>disconnectFn(...a)` y declara los `vi.fn()`):

```typescript
it("connect exitoso conecta y carga", async () => {
  connectFn.mockResolvedValue(true);
  checkHealth.mockResolvedValue(true);
  fetchPages.mockResolvedValue([{ id: "a", title: "A" }]);
  await useNotion.getState().connect("tok");
  expect(connectFn).toHaveBeenCalledWith(expect.anything(), "tok");
  expect(useNotion.getState().connected).toBe(true);
  expect(useNotion.getState().pages).toEqual([{ id: "a", title: "A" }]);
});
it("connect inválido setea error", async () => {
  connectFn.mockResolvedValue(false);
  await useNotion.getState().connect("bad");
  expect(useNotion.getState().error).toBe("token inválido");
});
it("disconnect limpia estado", async () => {
  disconnectFn.mockResolvedValue(undefined);
  useNotion.setState({ connected: true, pages: [{ id: "a", title: "A" }] });
  await useNotion.getState().disconnect();
  expect(useNotion.getState().connected).toBe(false);
  expect(useNotion.getState().pages).toEqual([]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- notionChannel state/notion`
Expected: FAIL (no existen `connect`/`disconnect`)

- [ ] **Step 3: Write minimal implementation**

Append a `ui/src/transport/notionChannel.ts`:

```typescript
export async function connect(ws: WsClient, token: string): Promise<boolean> {
  return (await ws.request("notion.connect", { token })).connected;
}
export async function disconnect(ws: WsClient): Promise<void> {
  await ws.request("notion.disconnect", {});
}
```

En `ui/src/state/notion.ts`: importa con alias para evitar el choque de nombres —
`import { checkHealth, fetchPages, addPage, removePage, connect as connectApi, disconnect as disconnectApi } from "../transport/notionChannel";` — agrega `connect`/`disconnect` al type `NotionState` y al store:

```typescript
  connect: async (token: string) => {
    try {
      const ok = await connectApi(getWs(), token);
      if (ok) { await get().load(); }
      else { set({ connected: false, error: "token inválido" }); }
    } catch (e) { set({ error: msg(e) }); }
  },
  disconnect: async () => {
    try { await disconnectApi(getWs()); set({ connected: false, pages: [], error: null }); }
    catch (e) { set({ error: msg(e) }); }
  },
```

(agrega `connect: (token: string) => Promise<void>;` y `disconnect: () => Promise<void>;` a la interface `NotionState`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- notionChannel state/notion`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/notionChannel.ts ui/src/state/notion.ts ui/src/transport/notionChannel.test.ts ui/src/state/notion.test.ts
git commit -m "feat(notion): transport + store connect/disconnect"
```

---

### Task 4: `NotionPanel` — vista de conexión con input de token

**Files:**
- Modify: `ui/src/modules/notion/NotionPanel.tsx`
- Test: `ui/src/modules/notion/NotionPanel.test.tsx` (ajustar)

**Interfaces:**
- Consumes: `useNotion` `connect`/`disconnect` (Task 3).
- Produces: cuando `!connected` → vista de conexión (input password + "Conectar" + link a my-integrations + instructivo + error); cuando `connected` → header con "Desconectar" además de refrescar/+Nueva.

- [ ] **Step 1: Write/adjust the failing test**

El test actual tiene `it("sin conexión muestra 'conecta Notion'")` que espera el texto viejo — **reemplázalo** por la vista nueva. Ajusta `NotionPanel.test.tsx`:

```typescript
// reemplaza el test "sin conexión ..." por:
it("desconectado muestra input de token y conecta", () => {
  setState({ connected: false });
  render(<NotionPanel />);
  const input = screen.getByPlaceholderText(/secret/i);
  fireEvent.change(input, { target: { value: "tok-123" } });
  fireEvent.click(screen.getByText(/conectar/i));
  expect(connect).toHaveBeenCalledWith("tok-123");
});
it("conectado muestra desconectar", () => {
  setState({ connected: true, pages: [] });
  render(<NotionPanel />);
  fireEvent.click(screen.getByLabelText(/desconectar/i));
  expect(disconnect).toHaveBeenCalled();
});
```

Agrega `connect`/`disconnect` a los `vi.fn()` y al `setState` helper del test (que ya inyecta `load, add, remove` en `useNotion.setState`): incluye `connect, disconnect`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- NotionPanel`
Expected: FAIL (no hay input de token / botón conectar / desconectar)

- [ ] **Step 3: Write minimal implementation** — reescribe `ui/src/modules/notion/NotionPanel.tsx`

```tsx
import { useEffect, useState } from "react";
import { Plus, RefreshCw, FileText, LogOut } from "lucide-react";
import { useNotion } from "../../state/notion";
import { useStore } from "../../state/store";

export function NotionPanel() {
  const { connected, pages, error, load, add, connect, disconnect } = useNotion();
  const openTab = useStore((s) => s.openTab);
  const [adding, setAdding] = useState(false);
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");

  useEffect(() => { load(); }, [load]);

  if (!connected) {
    return (
      <div className="p-3">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Conectar Notion</div>
        <input type="password" autoFocus placeholder="Internal Integration Secret" value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && token) connect(token); }}
          className="mb-2 w-full rounded border border-border bg-background px-2 py-1 font-mono text-[11.5px]" />
        <button onClick={() => token && connect(token)} disabled={!token}
          className="mb-2 rounded bg-[#e0863f] px-3 py-1 text-[11.5px] font-semibold text-black disabled:opacity-50">
          Conectar
        </button>
        {error && <div className="mb-2 text-xs text-destructive">{error}</div>}
        <div className="text-[11px] leading-relaxed text-muted-foreground">
          Crea una integración interna en{" "}
          <a href="https://www.notion.so/my-integrations" target="_blank" rel="noreferrer" className="text-[#e0863f]">notion.so/my-integrations</a>,
          pega su secret aquí, y comparte tus páginas con la integración.
        </div>
      </div>
    );
  }

  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Notion</span>
        <div className="flex items-center gap-1">
          <button aria-label="desconectar" onClick={() => disconnect()} className="text-muted-foreground hover:text-foreground"><LogOut size={13} /></button>
          <button aria-label="refrescar" onClick={() => load()} className="text-muted-foreground hover:text-foreground"><RefreshCw size={13} /></button>
          <button onClick={() => setAdding(true)} className="flex items-center gap-1 text-[11px] font-semibold text-[#e0863f]"><Plus size={12} />Nueva</button>
        </div>
      </div>
      {adding && (
        <input autoFocus placeholder="URL de la página de Notion" value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && url) { add(url); setUrl(""); setAdding(false); } if (e.key === "Escape") setAdding(false); }}
          className="mb-2 w-full rounded border border-border bg-background px-2 py-1 font-mono text-[11.5px]" />
      )}
      {error && <div className="px-1 py-2 text-xs text-destructive">desconectado — {error}</div>}
      {pages.map((p) => (
        <button key={p.id} onClick={() => openTab({ id: `notion:${p.id}`, type: "page", label: p.title })}
          className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left hover:bg-accent">
          <FileText size={13} className="mt-0.5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-foreground">{p.title}</span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test + tsc + build + suite**

Run: `cd ui && npm test -- NotionPanel && cd ui && npx tsc --noEmit && npm run build && npm test`
Expected: PASS; tsc limpio; build ok; suite completa verde.

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/notion/NotionPanel.tsx ui/src/modules/notion/NotionPanel.test.tsx
git commit -m "feat(notion): panel de conexión con input de token + desconectar"
```

---

## Verificación final (post Task 4)

- [ ] Backend: `cd server && uv run pytest -q` → verde (150 previos + nuevos).
- [ ] Frontend: `cd ui && npm test` → verde; `npx tsc --noEmit` limpio; `npm run build` ok.
- [ ] E2E manual: levantar app; panel muestra "Conectar Notion"; pegar un token real → conecta y lista; "Desconectar" limpia. Token inválido → "token inválido".
- [ ] HANDOFF: nota corta de la mejora (opcional, o en el cierre de la próxima rebanada).

## Self-Review (notas del plan)

- **Cobertura del spec:** write/clear token + dep (T1), capability connect/disconnect con validación (T2), transport+store (T3), panel de conexión + desconectar (T4). Fuera de alcance (OAuth, rotación, múltiples tokens) no se implementa.
- **Sin fallos silenciosos:** token inválido → connected:false (no persiste); disconnect limpia; errores → envelope.
- **Reusa Fase 1:** `notion_token`, `make_client` inyectable, `_FakeClient` de los tests.
- **Choque de nombres** en el store resuelto con alias (`connectApi`/`disconnectApi`).
- **Test roto esperado:** el test viejo "conecta Notion" del panel se reemplaza por la vista de conexión — es intencional, no un regressor.
