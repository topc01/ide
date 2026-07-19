# Spec — Notion Fase 2 (edición estructural)

> Fecha: 2026-07-19. Segunda rebanada del módulo Notion (Fase 1 ya mergeada). Fase 1 editaba
> **texto** de bloques existentes (PATCH por id). Fase 2 hace persistir **cambios de estructura**:
> agregar bloques, borrar bloques, y editar el título de la página.

## Objetivo

Que el editor de una página de Notion se sienta "como Notion": escribir de corrido creando
bloques nuevos (Enter), borrar bloques, y editar el título — y que todo eso **persista** en
Notion. Hoy, cualquier cambio de estructura solo muestra un banner ("llega en Fase 2") y
re-sincroniza sin guardar. Fase 2 elimina ese banner y persiste de verdad.

## Decisiones tomadas (brainstorming 2026-07-19)

1. **Alcance: agregar + borrar bloques, sin reordenar.** Notion no tiene endpoint "mover"
   bloque; reordenar solo se logra borrando + re-insertando, lo que reasigna el id de Notion y
   pierde comentarios/sub-bloques. Se descarta por destructivo. El **orden relativo** de los
   bloques que quedan sí se respeta (vía el `after` del APPEND).
2. **Título editable** vía `pages.update` (properties.title). Es una property de la página, no
   un bloque → camino aparte del diff de bloques (canal `notion.setTitle`).
3. **No remontar el editor** (preservar el cursor mientras se escribe). En vez del `syncKey`
   remount de Fase 1, se mantiene un **mapa `clientId → notionId`** en el front. El remount
   queda solo como fallback de error duro.
4. **Bloques no soportados protegidos de borrado.** Los placeholders (`[bloque no soportado:
   image]`, …) llevan el id real de Notion. `diff_ops` **nunca** emite DELETE para un id en
   `unsupported`: la herramienta no destruye contenido que ni sabe representar. (Sin fallos
   silenciosos.)

## El problema de identidad (y la solución)

Fase 1 asume el invariante **id de bloque BlockNote = id de Notion**, lo que hace que el diff de
texto correlacione limpio por id. Al **agregar** bloques ese invariante se rompe: cuando el
usuario aprieta Enter, BlockNote crea el bloque con un **id de cliente** (no de Notion). Recién
al hacer APPEND, Notion devuelve el id real.

Solución: el front mantiene un mapa **`clientId → notionId`** (`idMap`) además de `loaded` (la
última foto sincronizada, con ids de Notion). El diff resuelve cada bloque del editor con ese
mapa antes de comparar:

```
nid = idMap[bid] ?? bid
```

Así un bloque nuevo que **ya se subió** en un save anterior no se vuelve a APPEND (evita
duplicados): se resuelve a su notionId y se compara para PATCH. Un bloque cuyo `bid` no está en
`loaded` ni en `idMap` es **nuevo** → APPEND.

## Arquitectura

Extiende el paquete `notion/` y la capability `notion` de Fase 1. No cambia la resolución de
token ni la conexión.

### Backend

**`notion/adapter.py` — nueva función pura `diff_ops(loaded, edited, unsupported_ids, id_map)`**
que reemplaza a `diff_text_ops`. `id_map` es `dict[str,str]` (clientId→notionId), default `{}`.
Devuelve `{"ops": [...]}` (el título va por canal aparte, no por el diff de bloques). Cada op es
uno de:

- `{"op": "patch", "notionId": str, "notionType": str, "richText": [...]}` — bloque existente
  con contenido cambiado (comportamiento de Fase 1, ahora bajo `op`).
- `{"op": "append", "clientId": str, "after": str | None, "notionType": str, "richText": [...],
  "props": {...}}` — bloque nuevo. `after` = id (de cliente o de Notion) del hermano inmediato
  anterior en el editor, o `None` si es el primero. `props` lleva lo específico del tipo
  (`level` para heading, `checked` para to_do, `language` para code).
- `{"op": "delete", "notionId": str}` — bloque que estaba en `loaded` y ya no está en el editor.
  **Nunca** se emite para un id en `unsupported_ids`.

Reglas de `diff_ops`:
- Recorre `edited` **en orden** para poder calcular el `after` de cada nuevo (el `after` es el
  id resuelto del bloque previo en la lista, sea existente o recién insertado).
- Un bloque de `edited` cuyo id resuelto está en `loaded` → PATCH si su contenido difiere.
- Un bloque de `edited` cuyo id resuelto **no** está en `loaded` → APPEND.
- Un id de `loaded` ausente de `edited` (resolviendo el idMap inverso) y **no** en
  `unsupported_ids` → DELETE. Los `unsupported_ids` presentes en `loaded` se ignoran para DELETE.

**`notion/client.py` — dos funciones nuevas** (mismo patrón que `patch_block_text`, incl.
traducción 429 `APIResponseError` → `RateLimited`):
- `async append_block(client, parent_id, after, notion_type, rich_text, props) -> str` — llama
  `blocks.children.append(block_id=parent_id, children=[bloque], after=after)` y devuelve el id
  del bloque creado (`response["results"][0]["id"]`). Si `after` es `None`, se omite el kwarg
  (append al final). Construye el JSON del bloque según `notion_type`+`props`+`rich_text`.
- `async delete_block(client, notion_id) -> None` — llama `blocks.delete(block_id=notion_id)`.

**`notion/client.py` — `set_page_title`**:
- `async set_page_title(client, page_id, title) -> None` — `pages.update(page_id=page_id,
  properties={"title": {"title": [{"text": {"content": title}}]}})`. (Traducción 429 igual.)

**`capabilities/notion.py` — `save` reescrito** (canal `notion.save`):
- Recibe `{pageId, loaded, edited, unsupportedIds, idMap}`.
- Corre `diff_ops` → lista de ops.
- Aplica ops **secuencialmente** por el `RateLimitedRunner`, en orden, manteniendo un mapa
  local `minted: dict[str,str]` (clientId→notionId de lo recién creado). Para cada APPEND
  resuelve `after`: si el `after` es un clientId ya en `minted`, usa su notionId (así el 2º
  bloque nuevo consecutivo se ancla al id recién minteado del 1º); si es un notionId (bloque
  existente), lo usa tal cual; si es `None`, append al final. Registra `minted[clientId] =
  nuevo_id`.
- Cada op captura su error (rate limit u otro `APIResponseError`) y se acumula en `failed`
  **sin cortar** el resto (best-effort; el front reintenta por auto-diff).
- Devuelve `{"appended": [{"clientId": ..., "notionId": ...}], "deleted": [notionId, ...],
  "patched": [notionId, ...], "failed": [{"op": ..., "id": ..., "message": ...}]}`.

**`capabilities/notion.py` — `setTitle`** (canal `notion.setTitle`):
- Recibe `{pageId, title}` → `set_page_title` → `{"ok": true}`. Error → envelope.

Errores de transporte/red → envelope `{type:"error",...}` (sin fallos silenciosos). Los fallos
por-op de Notion (rate limit, permiso) viajan en `failed`, no como excepción global.

### Frontend

- **`transport/notionChannel.ts`**:
  - `savePage(ws, pageId, loaded, edited, unsupportedIds, idMap)` → nuevo shape de respuesta
    `{appended, deleted, patched, failed}`.
  - `setTitle(ws, pageId, title) -> Promise<void>`.
- **`main/NotionPageTab.tsx`**:
  - Mantiene `idMap` (estado, `Record<string,string>`) además de `loaded`/`unsupported`.
  - `onChange` (debounced ~800ms): llama `savePage(..., idMap)`. Con la respuesta:
    - fusiona `appended` en `idMap` (clientId→notionId);
    - actualiza `loaded` para reflejar el estado nuevo (los bloques aplicados: appended con su
      notionId, deleted quitados, patched con el contenido nuevo). Los `failed` **no** se
      incorporan a `loaded` → el próximo diff los reintenta solo.
    - **No** remonta el editor (sin `syncKey++`) salvo error duro.
  - **Título editable**: el header pasa de `<span>` a un input controlado; on blur / debounce
    llama `setTitle`. Sin bloques → sigue el mismo camino.
  - Se **elimina** el banner "los cambios de estructura llegan en Fase 2".

## Flujo de datos (agregar un bloque)

Usuario escribe párrafo, Enter (BlockNote crea bloque con clientId `c1`), sigue escribiendo →
debounce → `onChange` → `savePage(pageId, loaded, edited, unsupported, idMap={})` →
`diff_ops` ve `c1` no está en loaded/idMap → APPEND `after=<id del bloque previo>` →
`blocks.children.append` → Notion devuelve `n1` → respuesta `{appended:[{clientId:"c1",
notionId:"n1"}], ...}` → front: `idMap["c1"]="n1"`, `loaded` incorpora el bloque. Próxima
edición del mismo bloque → `diff_ops` resuelve `c1`→`n1`, existe en loaded → PATCH (no
re-APPEND).

## Manejo de errores

- Op individual falla (429 agotado, permiso) → va en `failed`, no corta las demás. El front no
  incorpora ese cambio a `loaded` → se reintenta en el próximo save. Si persiste, el usuario ve
  estado "error al guardar".
- Error de red/transporte → envelope → "desconectado".
- `setTitle` falla → envelope → estado de error en el header, el título del editor no se pisa.

## Plan de tests (TDD)

**Backend (`server/`):**
1. `adapter.diff_ops`: PATCH de existente cambiado; APPEND de bloque nuevo con `after` = id del
   previo; dos nuevos consecutivos → el 2º tiene `after` = clientId del 1º; DELETE de bloque
   quitado; **unsupported nunca se borra** (id en loaded+unsupported ausente de edited → sin
   DELETE); `id_map` resuelve clientId→notionId (bloque ya subido no re-APPEND, sí PATCH).
2. `client.append_block`: arma el JSON por tipo, pasa `after`, devuelve el id creado; omite
   `after` si es `None`; 429 `APIResponseError` → `RateLimited`. `client.delete_block`: llama
   `blocks.delete`; 429 → `RateLimited`. `client.set_page_title`: arma properties.title; 429 →
   `RateLimited`. (Fake client.)
3. Capability `notion.save`: ops mixtas (append+delete+patch) se aplican en orden vía el runner;
   `after` de nuevos consecutivos se resuelve contra `minted`; una op que falla va a `failed`
   sin cortar el resto; respuesta tiene `appended/deleted/patched/failed`. `notion.setTitle`
   éxito → `{ok:true}`.

**Frontend (`ui/`):**
4. `notionChannel.savePage` (nuevo shape con idMap) y `setTitle` (ws mock).
5. `NotionPageTab`: tras un save con `appended`, el `idMap` se fusiona y un segundo save del
   mismo bloque nuevo no lo re-envía como append (se envía el idMap correcto); el editor **no**
   se remonta en happy path (el `key`/syncKey no cambia); título editable llama `setTitle`; el
   banner de Fase 2 ya no se renderiza.

## Limitaciones conocidas (deuda para una Fase 2.1)

- **Cambio de tipo/props de un bloque existente con texto idéntico no se persiste.** El diff
  decide PATCH comparando solo `content` (texto). Si el usuario convierte paragraph→heading,
  **togglea el checkbox de un to_do existente**, o cambia `code.language` sin tocar el texto, no
  se emite ninguna op y el cambio se descarta. Es una frontera heredada de Fase 1 (la edición de
  bloques existentes es texto-only). El sub-caso del checkbox es el más filoso (acción común) y
  es el primer candidato a fast-follow: la detección es trivial (comparar también
  `_notion_type`/`_append_props` del bloque cargado), pero el fix completo requiere que
  `patch_block_text` mande los props y verificar la semántica de cambio de tipo vía `blocks.update`.
- **Un bloque nuevo insertado antes del primer bloque existente aterriza al final.** Notion no
  tiene "prepend"; con `after=None` el APPEND va al final. Escribir una línea nueva arriba de todo
  la reordena al fondo. Consistente con "sin reordenar".
- **Un nuevo consecutivo cuyo predecesor falló** apunta su `after` a un clientId no minteado →
  Notion lo rechaza y también cae en `failed`. Se auto-cura en el próximo save (re-fetch/reintento);
  no corrompe datos.

## Fuera de alcance

- Reordenar bloques (mover un bloque existente a otra posición).
- Crear/editar tipos de bloque no soportados (imágenes, tablas, DBs, synced, embeds) — siguen
  como placeholders inertes, ahora además protegidos de borrado.
- Sub-bloques anidados (children de un bloque) — Fase 1/2 trabajan el primer nivel.
- Deshacer/rehacer con conciencia de Notion, resolución de conflictos multi-cliente.

## Fidelidad de UI

Se mantiene el look de Fase 1 (editor BlockNote tematizado, header ámbar `#e0863f`). El título
pasa a input editable con el mismo idiom de los inputs existentes; sin banner. El estado
"guardando…/guardado/error" del header se conserva.
