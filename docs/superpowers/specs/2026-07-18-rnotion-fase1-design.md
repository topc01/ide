# Spec — R-Notion Fase 1: lectura + edición de texto (API oficial + BlockNote)

> Fecha: 2026-07-18. Fase 1 de la integración Notion (era ítem "Notion" del rail, hoy stub).
> Fase 2 (edición estructural: agregar/borrar/reordenar bloques) va después en su ciclo.
> Módulo hermano futuro: **Tasks** (markdown local en `.ide/tasks/`), rebanada aparte.

## Objetivo

Entregar el ítem "Notion" del rail: una **lista curada** de páginas de Notion (agregadas por
URL), que al abrirse se **renderizan con un editor de bloques (BlockNote)** fiel al look de
Notion, y permiten **editar el texto de los bloques existentes** con sincronización de vuelta a
Notion vía la **API oficial**, respetando el rate limit (~3 rps).

## Decisiones tomadas (brainstorming 2026-07-18)

1. **API oficial solamente.** Token de integración oficial; SDK `notion-client` (Python).
   Prohibido: API privada, `token_v2`, scraping, `recordMap`/react-notion-x.
2. **Backend = proxy/orquestador.** Python consume el SDK oficial y expone endpoints al front
   por el bus WS existente. La conversión de esquemas vive en el backend (puro, testeable).
3. **UI = BlockNote** (`@blocknote/react`), editor de bloques estilo Notion sobre ProseMirror
   — resuelve selección/caret/Enter/Backspace. Descartada la Opción contentEditable (tar pit).
4. **Fase 1 = lectura + edición de TEXTO de bloques existentes.** Los cambios estructurales
   (agregar/borrar/reordenar bloques) NO se sincronizan en Fase 1: se **avisan explícitamente**
   y se re-sincroniza desde el servidor (sin fallos silenciosos). Estructural = Fase 2.
5. **Lista curada local por URL.** El botón "+" agrega una página existente por su link (no crea
   páginas). La lista (ids + título cacheado) vive en `.ide/notion.json`.
6. **Bloques soportados (Fase 1):** paragraph, heading_1/2/3, bulleted_list_item,
   numbered_list_item, to_do, quote, code, divider; rich text inline (bold, italic,
   strikethrough, underline, code, link, color). **No necesarios / inertes:** synced blocks,
   bases de datos, embeds, columnas, toggles, callouts, imágenes → se muestran como placeholder
   read-only "bloque no soportado", **nunca se editan ni se borran** (el motor de diff los
   ignora).
7. **Rate limit** (~3 rps): debounce en el front + **cola serializada en el backend** con
   backoff en 429.
8. **Token a nivel global** `~/.ide/config.toml [notion].token`, con override local
   (`.ide/config.toml`) y env `NOTION_TOKEN`. Sin token / inválido → panel "conectá Notion".

## Arquitectura

Molde de plugin de R4/R5a: paquete backend `notion/` + capability en `app.py` + transport +
store Zustand + módulo del rail + tab. La novedad: un **cliente HTTP a un servicio externo**
(Notion) con **cola de rate-limit**, y una **dependencia de frontend** (BlockNote).

### Backend — paquete `server/ide_server/notion/`

**Deps nuevas:** `notion-client` (SDK oficial Python; usa httpx, ya presente). Se agrega a las
dependencias principales de `server/pyproject.toml`.

- `config.py` — `notion_token(home, root) -> str | None`: resuelve el token en orden env
  `NOTION_TOKEN` → local `.ide/config.toml [notion].token` → global `~/.ide/config.toml
  [notion].token`. `None` si no hay.
- `refs.py` — lista curada en `<root>/.ide/notion.json` (`{"pages":[{"id","title"}]}`):
  `list_refs(root)`, `add_ref(root, id, title)`, `remove_ref(root, id)`, y
  `parse_page_id(url_or_id) -> str` (extrae el UUID de 32 hex de un link de Notion; error claro
  si no matchea).
- `adapter.py` — **puro, testeable** (la carne):
  - `notion_blocks_to_blocknote(blocks: list[dict]) -> list[dict]` — mapea el JSON oficial de
    bloques al schema de BlockNote para el set soportado; los no soportados → un bloque
    placeholder `{type:"unsupported", props:{notionType, notionId}}` (inerte).
  - `notion_richtext_to_inline(rich_text) -> list[dict]` / `inline_to_notion_richtext(inline)
    -> list[dict]` — el par inline (annotations ↔ styles de BlockNote), bidireccional.
  - `diff_text_ops(loaded: list[dict], edited: list[dict]) -> {ops, structural}` — compara el
    doc BlockNote cargado vs el editado **por id de bloque**: para cada bloque existente cuyo
    texto/inline cambió → una op `{notionId, richText}` (PATCH). Si aparecen/desaparecen ids
    (cambio estructural) → `structural=True` (el front lo avisa; no se emiten ops de esos).
    Bloques `unsupported` nunca generan ops.
- `client.py` — `async_client(token) -> AsyncClient` (SDK oficial). `async fetch_page(client,
  page_id) -> {title, blocks}`: `blocks.children.list` paginado (page_size 100, sigue
  `next_cursor`) + recursión en `has_children` para el set soportado; `pages.retrieve` para el
  título. `async patch_block_text(client, notion_id, notion_type, rich_text)`:
  `blocks.update(block_id, **{notion_type: {"rich_text": rich_text}})`.
- `queue.py` — `RateLimitedRunner`: cola async **serializada** que despacha callables a ≤3 rps
  (token-bucket con reloj inyectable) y hace backoff ante `APIResponseError` 429 (respeta
  `Retry-After`). Un runner por proceso; las ops de un `notion.save` se encolan y se aplican en
  orden. Fallo parcial → se reporta qué ops fallaron (envelope), el front re-fetchea.

**Capability `capabilities/notion.py`** (registrada en `app.py`):
- `notion.health` → `{connected: bool}` (hay token y `users.me` responde; error de token →
  `connected:false`, no crash).
- `notion.list` → `{pages}` (lista curada).
- `notion.add {url}` → `{page}` (parse id → `pages.retrieve` título → `add_ref`).
- `notion.remove {id}` → `{ok}`.
- `notion.page {id}` → `{title, blocks}` (blocks = doc BlockNote via adapter).
- `notion.save {id, loaded, edited}` → `{applied, structural, failed}`: el front manda el doc
  BlockNote `loaded` (original) y `edited` (actual); el backend corre `diff_text_ops(loaded,
  edited)` y encola los PATCH. Devuelve `structural:true` si hubo cambios estructurales (el
  front avisa) y `failed` con las ops que fallaron.

Errores de red/API/token → envelope `{type:"error",...}` vía `bus.py`. Sin fallos silenciosos.

### Frontend

**Deps nuevas:** `@blocknote/core`, `@blocknote/react`, `@blocknote/mantine` (+ sus CSS).

- `transport/notionChannel.ts` — `checkHealth`, `fetchPages`, `addPage(url)`, `removePage(id)`,
  `fetchPage(id)`, `savePage(id, loaded, edited)`. Tipos `NotionRef {id,title}`,
  `BlockNoteDoc = unknown[]` (el JSON de BlockNote).
- `state/notion.ts` (Zustand) — `{connected, pages, loading, error, load, add, remove}` (lista);
  el estado por-página (doc cargado, dirty, saving, structuralNotice) vive en el tab.
- `modules/notion/NotionPanel.tsx` — reemplaza el stub. Estado "conectá Notion" si
  `!connected`. Botón **"+ Nueva"** → input inline para pegar la **URL** → `add`. Lista de
  páginas (ícono, título, preview), fiel al mockup (231-251). Click → `openTab({id:'notion:'+id,
  type:'page', label:title})`. Estado de error, botón refrescar. `register.tsx`; se quita
  `notion` de `stubs.tsx`; import en `App.tsx` y `registry.test.ts`.
- `main/NotionPageTab.tsx` — `MainPanel` rutea `type==="page"` acá. Inicializa BlockNote con el
  doc de `notion.page`. **Título editable** (PATCH properties — o Fase 2; en Fase 1 el título es
  read-only para acotar) — **decisión: título read-only en Fase 1**, solo contenido de texto.
  `onChange` con **debounce (~800ms)** → `savePage(loaded, edited)`; indicador de estado
  (guardado / guardando / error). Si `structural` → banner no-bloqueante "los cambios de
  estructura (agregar/quitar bloques) llegan en Fase 2; se guardaron las ediciones de texto" y
  re-fetch para re-alinear. Bloques `unsupported` → render placeholder read-only.

## Flujo de datos

`NotionPanel` monta → `notion.health` + `notion.list`. Click página → tab → `NotionPageTab` →
`notion.page` → adapter → BlockNote. Editás texto → onChange (debounce) → `notion.save {loaded,
edited}` → `diff_text_ops` → cola de rate-limit → `blocks.update` (PATCH) por bloque cambiado →
`{applied, structural, failed}`. Estructural → banner + re-fetch.

## Manejo de errores

- Sin token / token inválido → `notion.health connected:false` → panel "conectá Notion".
- Error de red/API → envelope → tab muestra error, no guarda datos falsos como guardados.
- 429 → la cola hace backoff (`Retry-After`) y reintenta; si agota → op falla → reportada.
- Fallo parcial de save → `failed` no vacío → el front avisa y re-fetchea (estado real, no
  optimista mentido).
- Cambio estructural en Fase 1 → banner explícito + re-sync (nunca drop silencioso).
- Bloque no soportado → placeholder inerte, jamás se le emite una op.

## Plan de tests (TDD, un commit por tarea)

1. `notion/config.py`: resolución de token (env > local > global) con `tmp_path`.
2. `notion/refs.py`: `parse_page_id` (varias formas de URL + id crudo + error), CRUD de
   `.ide/notion.json`.
3. `notion/adapter.py` (el grueso, puro): `notion_blocks_to_blocknote` para cada tipo
   soportado + placeholder para no soportado; `notion_richtext_to_inline` /
   `inline_to_notion_richtext` (bold/italic/link/code, round-trip); `diff_text_ops` (texto
   cambiado → op; estructural → flag; unsupported → sin op).
4. `notion/queue.py`: `RateLimitedRunner` con reloj mockeado — respeta ≤3 rps, serializa,
   backoff en 429 (excepción simulada con `Retry-After`).
5. `notion/client.py`: `fetch_page`/`patch_block_text` con el SDK **mockeado** (AsyncClient
   stub) — paginación (`next_cursor`), recursión `has_children`, forma del PATCH.
6. Capability `notion.*`: health/list/add/remove/page/save con cliente y refs mockeados;
   envelopes de error (sin token, API error).
7. Frontend `notionChannel` + `state/notion` (load/add/remove, guard de error).
8. `NotionPanel`: estado conectá-Notion, lista, +URL agrega, click abre tab, error.
9. `NotionPageTab`: render de BlockNote desde doc, debounce→save (mock), banner estructural,
   indicador de estado. (BlockNote se mockea/monta según convenga en jsdom.)

## Fuera de alcance Fase 1 (→ Fase 2)

- Edición **estructural**: agregar/borrar/reordenar bloques (APPEND `after`/DELETE + id-map
  `blocknote↔notion`). En Fase 1 se avisan, no se sincronizan.
- Editar el **título** (PATCH properties) — read-only en Fase 1.
- Bloques no soportados (synced/DB/embed/columnas/toggles/callouts/imágenes) — **no
  necesarios** (inertes).
- Crear páginas nuevas (solo se agregan existentes por URL).
- Colaboración en vivo / resolución de conflictos (last-write-wins + re-fetch).

## Fidelidad de UI

BlockNote tematizado a la identidad 1a ámbar/terminal donde sea razonable (o su tema por
defecto en Fase 1 si tematizar es costoso — decisión del plan). Panel fiel al mockup
(`docs/design/handoff/mockup.dc.html` 231-251). Tokens en `docs/design/REFERENCES.md`.

## Riesgos anotados

- **Dependencia externa (Notion) + API oficial:** rate limit, latencia, token que expira. La
  cola + envelopes acotan el riesgo; los tests mockean el SDK (no se pega a Notion en CI).
- **Nueva dep de frontend pesada (BlockNote):** aumenta el bundle; aceptado por la decisión de
  UX. Evaluar tematización 1a en el plan.
- **Diff por id de bloque:** depende de que BlockNote preserve los ids de los bloques cargados
  al editar texto. A validar en el plan; si BlockNote regenera ids, el diff usa el orden/posición
  como fallback y cualquier ambigüedad → se trata como estructural (re-sync), nunca PATCH al
  bloque equivocado.
