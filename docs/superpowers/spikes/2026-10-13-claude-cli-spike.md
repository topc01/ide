# Spike: supuestos del CLI `claude` para sesiones-carpeta (2026-10-13)

Versión probada: `claude` 2.1.296. Todo con `claude -p` (no interactivo), `</dev/null`, workspace
temporal `/private/tmp/claude-501/spike.XXXX/.ide/sessions/<id>/` (cwd no-git). Login de suscripción, sin API key.

## 1. CLAUDE.md heredado por walk-up desde carpeta no-git — ✅
- Cmd: `cd .ide/sessions/s1 && claude --settings .../analyze.json -p "¿Cuál es la palabra clave de tu CLAUDE.md? ..."`
- Resultado: respondió **PINGÜINO**; el CLAUDE.md estaba en `.ide/sessions/CLAUDE.md` (carpeta padre de `s1`), así que el walk-up hacia arriba funciona aunque no haya git.
- Ajuste: ninguno. El "mapa de repos" puede vivir en `.ide/sessions/CLAUDE.md`.

## 2. `--settings` allow/deny aplica en `-p` desde cwd no-git — ✅
- Cmd: `claude --settings analyze.json -p "... echo hola ... ls / ... crea TICKET.md"`
- `echo hola` (allow `Bash(echo:*)`): ejecutó sin pedir permiso, imprimió `hola`.
- `ls /` (no está en allow): **bloqueado** (en `-p` lo no permitido se deniega solo). El modelo informó que solo puede listar dentro del directorio de la sesión.
- `rm TICKET.md` (deny `Bash(rm:*)`): mensaje exacto `Permission to use Bash with command rm TICKET.md has been denied.`; el archivo no se tocó.
- Sin regla de escritura: `Claude requested permissions to write to <cwd>/TICKET.md, but you haven't granted it yet.` (el archivo no se crea).
- Ajuste: el fallback `sessions/<id>/.claude/settings.json` NO hace falta; pasar `--settings` funciona. Ojo: el `--settings` relativo se reporta como `../../permissions/analyze.json`; pasar ruta absoluta igual.

## 3. Patrón `Edit(**/TICKET.md)` / `Write(**/TICKET.md)` — ✅ con ajuste
- Con `analyze.json` original, `claude` imprime en stderr: `Permission allow rule (...): Write(**/TICKET.md) is not matched by file permission checks — only Edit(path) rules are. Use Edit(**/TICKET.md) instead (Edit rules cover all file-editing tools).`
- Con un perfil que tiene **solo** `Edit(**/TICKET.md)` (sin Write): creó `TICKET.md` sin pedir permiso, y `OTRO.md` fue **denegado** (el patrón limita al nombre).
- No hizo falta probar `Write(TICKET.md)` / `Write(./TICKET.md)`: las reglas `Write(...)` no se evalúan.
- Ajuste (Task 3 / perfiles): usar **solo `Edit(**/TICKET.md)`** y eliminar `Write(**/TICKET.md)` del seed de `analyze.json` (genera warning). Un `Edit(...)` cubre Write/Edit.

## 4. Nombre del dir en `~/.claude/projects` y `--continue` — ✅ con ajuste
- `claude -p "Recuerda el número 4711."` y luego `claude --continue -p "¿Qué número...?"` en el mismo cwd → respondió **4711**. `--continue` es por cwd.
- Dir real: `-private-tmp-claude-501-spike-lTYL--ide-sessions-s1` (nótese que el `.` de `spike.lTYL` y el de `.ide` también pasan a `-`).
- Python `re.sub(r"[^A-Za-z0-9]", "-", str(path))`:
  - path **resuelto** `/private/tmp/claude-501/spike.lTYL/.ide/sessions/s1` → `-private-tmp-claude-501-spike-lTYL--ide-sessions-s1` (coincide exacto).
  - path **sin resolver** `/tmp/claude-501/spike.lTYL/.ide/sessions/s1` → `-tmp-claude-501-spike-lTYL--ide-sessions-s1` (NO coincide: claude resuelve symlinks).
- Ajuste (Task 6, `encode_project_dir`): la regex es correcta pero hay que aplicarla sobre `Path(cwd).resolve()` (en macOS `/tmp` y `/var` son symlinks a `/private/...`).

## 5. Nombres de herramientas MCP de Notion — ✅
Prefijo `mcp__claude_ai_Notion__` (con guion bajo en `claude_ai_Notion`, y herramientas con guiones `notion-...`). Para el seed de `analyze.json` (Task 3):
- fetch: `mcp__claude_ai_Notion__notion-fetch`
- search: `mcp__claude_ai_Notion__notion-search`
- query data sources: `mcp__claude_ai_Notion__notion-query-data-sources` (también `notion-query-multiple-data-sources`, `notion-query-meeting-notes`)
- otros de lectura útiles: `notion-get-comments`, `notion-get-users`, `notion-get-teams`, `notion-list-recent-pages`.
- (Hay además tools de escritura: `notion-update-page`, `notion-create-pages`, etc. — no incluirlas en allow de `analyze`.)
- Ajuste: usar exactamente estos nombres en `allow`; nota que se ven en `-p` sin config extra (conector de claude.ai de la cuenta).

## 6. `--permission-mode bypassPermissions` no interactivo — ✅
- Cmd: `claude --permission-mode bypassPermissions -p "Ejecuta: echo bypass-ok"` → ejecutó y devolvió `bypass-ok`, rc=0, sin diálogo de aceptación.
- Ajuste: ninguno.

## Resumen de ajustes para tareas posteriores
1. Perfiles: solo `Edit(**/TICKET.md)`; quitar `Write(**/TICKET.md)`.
2. `encode_project_dir`: `re.sub(r"[^A-Za-z0-9]", "-", str(Path(cwd).resolve()))`.
3. Sin fallback `.claude/settings.json`: `--settings <ruta absoluta>` funciona.
4. Nombres Notion: `mcp__claude_ai_Notion__notion-fetch|search|query-data-sources`.
5. Cosas a tener en cuenta: en `-p` sin stdin, `claude` espera 3s ("no stdin data received") — redirigir `</dev/null`.
