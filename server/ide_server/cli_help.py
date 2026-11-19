# server/ide_server/cli_help.py
"""`ide <comando> --help`: qué hace, cómo se usa y ejemplos. El CLAUDE.md de las sesiones dice qué comando usar y
cuándo; el detalle de uso vive aquí. Un error de argumentos también muestra los ejemplos del comando."""
from __future__ import annotations
import argparse
import sys

# clave = el comando sin `ide` ("review publish"); valor = (descripción, ejemplos/notas). Va tal cual (saltos de línea).
HELP: dict[str, tuple[str, str]] = {
    "repo": ("Los repos de tu sesión (un worktree por repo).", """\
ejemplos:
  ide repo add finnecto-api                 # worktree en la rama $IDE_DEV_BRANCH (<login>/d12-<nombre>); corre su setup
  ide repo add finnecto-embed --branch x    # en otra rama
  ide repo rm finnecto-embed                # lo saca (--force si tiene cambios sin commitear)
Si el desarrollo toca varios repos, agrega cada uno: queda fullstack (una card, PRs por repo), mismo nombre de rama."""),
    "push": ("Sube a origin la rama de tus worktrees (sin cd; nunca la principal). Úsalo en vez de `git push`.", """\
ejemplos:
  ide push                                  # todos los repos de la sesión
  ide push finnecto-api --force             # --force-with-lease, después de un rebase
  ide push finnecto-api --branch tpc/d12-x-develop   # otra rama local (p.ej. las de un stack o un backport)"""),
    "pr": ("Mueve una PR tuya a otra base (p. ej. sacar una PR apilada a su propia rama desde develop): frena si toca "
           "archivos que solo están en la base vieja o si sus commits chocan (sin mover nada), renumera migraciones, "
           "sube con --force-with-lease, cambia la base en GitHub y la deja en tu desarrollo.", """\
ejemplos:
  ide pr move api#5900 --onto develop       # la saca del stack a develop
  ide migrations check --base develop       # revisar las migraciones contra develop antes de moverla"""),
    "backport": ("El backport de un hotfix, en el mismo desarrollo: crea un worktree extra en tu carpeta de worktrees "
                 "(<repo>-develop) con la rama <tu rama>-develop desde origin/develop, copia los commits del hotfix "
                 "(cherry-pick -x) y la sube.", """\
ejemplos:
  ide backport finnecto-api                  # hotfix sobre main → backport a develop
  ide backport finnecto-api --onto staging --from main
Si el cherry-pick choca, queda a medias: resuelve en el worktree extra, `git -C <ruta> cherry-pick --continue` e
`ide push <repo> --branch <tu rama>-develop`. Después abre la PR con base develop («backport de #…» en el body) y
declara que van juntas (`ide dep add` en las dos direcciones)."""),
    "update": ("Pone al día tu rama sobre su base cuando hace falta: la PR está en conflicto, su madre del stack se "
               "mergeó, o está atrás y todavía no tiene aprobación (el CI corre recién con una aprobación: rebasear "
               "antes no cuesta nada). Aprobada y solo atrás, se niega (vuelve a correr el CI y puede descartar la "
               "aprobación), salvo con --behind, cuando el usuario lo pidió explícito.", """\
ejemplos:
  ide update --dry-run                      # dice qué haría
  ide update finnecto-api
  ide update finnecto-api --behind          # aprobada: el usuario pidió ponerla al día igual (no a mano)
En un stack mira toda la línea: si la que necesita ponerse al día es una de abajo (o la tuya tiene PRs encima), la
rebasea y re-apila encima todo lo que cuelga de ella, también las hermanas en otros worktrees.
Si un rebase choca, queda a medias: resuelve, `git rebase --continue` y vuelve a correr `ide update <repo>` (sigue
desde ahí y sube todo)."""),
    "migrations": ("Las migraciones de tu rama contra develop: cada nueva va después de la última de su app y depende "
                   "de ella.", """\
ejemplos:
  ide migrations check                      # antes de pedir revisión
  ide migrations renumber finnecto-api      # si chocan: renumera, corrige dependencias, commitea y sube (sin preguntar)"""),
    "merge": ("Mergea una PR (squash): revisa sus migraciones, la pone al día si está en conflicto y restackea las de "
              "arriba. Lo hace el usuario; tú solo si te lo pide explícito.", """\
ejemplo:
  ide merge api#5092                        # después verifica en GitHub que quedó mergeada"""),
    "db": ("Una consulta de solo lectura a la base de prod o staging.", """\
reglas (si no, el permiso no lo cubre y se frena):
  - Va SOLO, como único comando de la línea: sin pipes (| head), sin ;, sin &&, sin `cd … &&` delante, sin loops.
  - Sin comandos de psql (nada con \\). Filtra, ordena y limita en el SQL.
  - Una base por comando: prod y staging van en dos comandos.
  - Antes de escribir el SQL, mira las columnas reales: `mcp__claude_ai_Finnecto_CX__describe_schema` (table=<tabla>;
    sin table, la lista; environment=staging para staging). No adivines nombres de columnas ni de tablas.
ejemplos:
  ide db prod "select id, name from companies_company where name ilike '%acme%' limit 20"
  ide db staging "select count(*) from invoices_invoice where status = 'paid'"
  ide db prod "select * from payments_payment where company_id = 12" --csv --out pagos.csv
      # queda en attachments/db/pagos.csv (el usuario lo ve en Adjuntos); léelo en otro comando"""),
    "script": ("Corre un script del repo que termina (test, build, …): espera a que acabe.", """\
ejemplos:
  ide script build finnecto-api
Para levantar un servidor (`run`), usa `ide server start <bloque> run`: un run no termina."""),
    "session": ("Sesiones del IDE.", """\
ejemplos:
  ide session ls                            # sesiones y su estado
  ide session new --title "Exportar pagos a CSV"   # otro desarrollo (cualquier sesión puede); cuéntaselo al usuario
  ide session send 12 --prompt-file - <<'EOF'      # le encola un prompt a la sesión #12
  …
  EOF
Solo la principal: `ide session new --if-missing --notion <url> --template ticket --vars-file -` y
`ide session new --review <pr-url>`."""),
    "session send": ("Encola un prompt a la sesión de un desarrollo (id o #número).", """\
ejemplos:
  ide session send 12 --prompt "¿en qué quedó la migración?"
  ide session send 12 --prompt-file - <<'EOF'
  texto de varias líneas
  EOF
  ide session send 12 --prompt-file attachments/pedido.md   # un archivo de tu carpeta de sesión"""),
    "session propose": ("Propone por Telegram mandarle un prompt a una sesión (se manda con el Sí del usuario).",
                        "ejemplo:\n  ide session propose 12 --prompt-file - <<'EOF'\n  …\n  EOF"),
    "status": ("Marca el estado del desarrollo (lo demás lo deduce el IDE solo: draft, revisión, merge, si trabajas o "
               "esperas).", """\
estados que marcas tú:
  investigating                 al empezar, si todavía no hay código
  ready-for-review              terminaste (las PRs siguen en draft; el usuario las manda a revisión)
  blocked -m "<de quién>"       dependes de afuera y ya no puedes avanzar (mejor: ide later add … --blocks)
  unblock                       se destrabó
  paused                        si el usuario lo pide
ejemplos:
  ide status investigating
  ide status blocked -m "definiciones de producto"
  ide status unblock
Nunca edites el `status:` de SESSION.md a mano."""),
    "dev status": ("Tu desarrollo en una tabla: por repo de la sesión, la rama del worktree, si tiene cambios sin "
                   "commitear o commits sin subir, y cuántos commits le faltan de su base; debajo, sus PRs abiertas "
                   "con revisión, CI, draft y posición en el stack. En vez de recorrer repos con git y PRs con gh.",
                   "ejemplos:\n  ide dev status\n  ide dev status --fetch      # trae origin antes (un fetch por repo)\n"
                   "Lo que te pidieron en las PRs (cambios, hilos): `ide review inbox`."),
    "review": ("Reviews en GitHub, en vez de `gh api` (lo frena el clasificador). En una sesión de ticket: `inbox`, "
               "`reply`, `resolve` y `add-reviewer` sobre las PRs de tu desarrollo. En una de revisión: además "
               "`publish` y `verdict`, sobre sus PRs. Córrelo solo, como único comando de la línea. <pr> = URL o "
               "<repo>#<n>.", """\
ejemplos:
  ide review inbox                          # qué te pidieron: cambios, hilos sin resolver, comentarios nuevos
  ide review publish api#5092 review.json   # pide cambios con comentarios en línea
  ide review verdict api#5092 approve --file comentario.md --why "una línea"   # aprobar: lo publica el usuario
  ide review reply api#5092 123456 "Listo, corregido"
  ide review resolve PRRT_kwDOabc --undo
  ide review add-reviewer api#5092 diegobustosk   # en una PR tuya en draft, además la saca de draft
Para verificar: gh pr view."""),
    "review publish": ("Publica una review que pide cambios, con sus comentarios en línea.", """\
el JSON es el de POST /repos/<o>/<r>/pulls/<n>/reviews:
  {"body": "…", "event": "REQUEST_CHANGES", "commit_id": "<sha de la cabeza>",
   "comments": [{"path": "app/x.py", "line": 42, "side": "RIGHT", "body": "…"}]}
Nunca event COMMENT (una review solo de comentarios no sirve). Aprobar: `ide review verdict … approve`.
Deja el veredicto registrado en el IDE.
ejemplo:
  ide review publish https://github.com/Finnecto/finnecto-api/pull/5092 review.json"""),
    "review verdict": ("Registra tu veredicto en el IDE (la ventana Aprobar / Pedir cambios de la card lo trae cargado). "
                       "Cada ronda pisa a la anterior.", """\
ejemplos:
  ide review verdict api#5092 approve --file comentario.md --why "cubre los 3 criterios, tests ok"
  ide review verdict api#5092 changes --file - --why "falta validar el tenant" <<'EOF'
  …
  EOF"""),
    "review inbox": ("Lo que te pidieron en las PRs abiertas de tu desarrollo, en un solo comando: por PR, la última "
                     "review que pide cambios de cada revisor (si es posterior a tu último commit), los hilos sin "
                     "resolver donde la última palabra no es tuya (con el id del comentario para `reply` y el del hilo "
                     "para `resolve`) y los comentarios generales de otros después de tu último commit. Lo que ya "
                     "atendiste sale en una línea «esperando al revisor».",
                     "ejemplos:\n  ide review inbox\n  ide review inbox --all      # también el detalle de las PRs sin pendientes"),
    "review reply": ("Responde en un hilo de review existente.",
                     "ejemplos:\n  ide review reply api#5092 123456 \"Hecho en abc123\"\n"
                     "  ide review reply api#5092 123456 --file - <<'EOF'\n  …\n  EOF"),
    "evidence": ("Pasos de prueba con capturas (módulo Evidencias). <n> = número del paso; --run elige la corrida "
                 "(default: la última).", """\
ejemplos:
  ide evidence plan --run PR <<'EOF'        # la guía: un ítem de lista por paso; 📸 = lleva captura
  - Entra a Pagos y filtra por «Programados» 📸
    detalle del paso (líneas de abajo)
  - Abre el pago #19 y revisa el candado 📸
  EOF
  ide evidence shot 1 attachments/pagos.png        # adjunta captura(s) a un paso (lo marca hecho)
  ide evidence shot 1 nueva.png --replace          # reemplaza las capturas obsoletas
  ide evidence check 2                              # paso hecho sin captura
  ide evidence edit 2 "texto nuevo" --detail "…" --shot   # corrige un paso (conserva sus capturas)
  ide evidence add "otro paso" --after 2 --shot
  ide evidence rm --step 3 --shot 1                 # saca una captura; --step 3 solo = el paso; sin nada = la corrida
  ide evidence ls                                   # corridas, pasos y rutas de las capturas
  ide evidence publish api#5092                     # comentario en la PR con pasos y capturas (verifica que subieron)
No edites ni borres los archivos a mano, ni armes el comentario o los --attach de gh tú. Si alguna vez armas un
`gh … --attach` (zsh): los --attach van en un array (args+=(--attach "$f") y "${args[@]}"), nunca en una variable de
texto, y a un gh que publica no le pongas | tail (escondería el error)."""),
    "ticket": ("El ticket de Notion del desarrollo.", """\
ejemplos:
  ide ticket set https://www.notion.so/…        # asocia el ticket (la card muestra su Status)
  ide ticket add-sub https://www.notion.so/…    # suma un subticket (p.ej. lo que quedó fuera)
  ide ticket rm-sub https://www.notion.so/…
  ide ticket callout --type evidence --title "Probado en staging" --body-file - <<'EOF'
  - qué se probó y qué se ve
  EOF
Desde la principal o tu terminal, antes del link va el desarrollo: ide ticket set 12 <url>."""),
    "ticket callout": ("Un callout al principio del ticket: decision (amarillo), pending (morado), evidence (verde). "
                       "Para una pregunta o pendiente, mejor `ide later add … --callout-file -` (crea los dos enlazados).",
                       """\
cuerpo: líneas «- …» (viñetas), «1. …», texto; **negrita** y [links](url).
ejemplo:
  ide ticket callout --type evidence --title "Etiqueta por correo en recepción" --body-file - <<'EOF'
  - Se recibe la OC y el correo llega con la etiqueta
  - [Captura](https://…)
  EOF"""),
    "later": ("Bloqueantes del desarrollo: decisiones (del usuario o a conversar con alguien) y pendientes (algo que "
              "se espera de alguien). Cada uno tiene su código: D3 (decisión), P4 (pendiente).", """\
ejemplos:
  ide later add "¿Filtramos por fecha de factura o de pago?" --with "Sebastián (CX)"
  ide later add "Credenciales del SFTP del cliente" --pending --with "Laura (CX)" --blocks
  ide later add "¿Qué hacemos con las facturas sin OC?" --with "Sebastián (CX)" --callout-file - <<'EOF'
  **Propuesta:** rechazarlas en FinnOps, porque …
  - Contexto: …
  - [Análisis](https://claude.ai/artifact/…)
  EOF
  ide later ls --mine
  ide later done D3 -m "se decidió por fecha de pago"
--blocks = ya no puedes avanzar en nada más: el desarrollo pasa a Bloqueado (y el ticket a Awaiting Client) hasta
que se cierre. El texto, corto; el análisis va en un artefacto (--artifact <link>), no en -m."""),
    "typecheck": ("Chequeo de tipos del proyecto entero (`npm run type-check` = vue-tsc) o build (`--build`) de un front, "
                  "de a uno entre todas las sesiones (si hay otro corriendo, espera) y con tope de 4 GB de memoria "
                  "(NODE_OPTIONS se reemplaza: no se puede subir). Cada uno se come varios GB: dos a la vez llenaron la "
                  "memoria de la Mac. El hook frena vue-tsc, `npm run type-check` y `npm run build` sueltos.",
                  "ejemplos:\n  ide typecheck                 # el único front de la sesión\n  ide typecheck finnecto-embed\n"
                  "  ide typecheck finnecto-embed --build"),
    "later edit": ("Edita un bloqueante abierto: solo cambia lo que pases. Una sesión, solo los de su desarrollo.",
                   "ejemplos:\n  ide later edit D3 --text \"¿Se avisa también al aprobador?\"\n"
                   "  ide later edit P4 --with \"Laura (CX)\" --no-blocks\n  ide later edit D3 -m \"\"          # le saca el contexto\n"
                   "  ide later edit P4 --decision                # pasa a decisión del usuario\n"
                   "El callout del ticket en Notion no cambia: si hace falta, edítalo allá."),
    "later add": ("Deja un bloqueante en el desarrollo de la sesión.", """\
ejemplos:
  ide later add "¿Filtramos por fecha de factura o de pago?" --with "Sebastián (CX)"
  ide later add "Accesos al ERP del cliente" --pending --with "Laura (CX)" --blocks
  ide later add "¿…?" --with "…" --artifact https://claude.ai/artifact/abc --callout-file attachments/callout.md
--callout-file: además, su callout al principio del ticket (la pregunta es el título; el cuerpo, la propuesta con
su porqué, el contexto mínimo y links). Una pregunta por bloqueante."""),
    "tour": ("El recorrido de lo que hiciste: el usuario lo abre desde la card («▶ recorrido») y un Chrome va por tus "
             "pantallas con un recuadro que le dice qué mirar; sus comentarios te llegan juntos al terminar.", """\
ejemplo:
  ide tour set --title "Retención de pagos desde Finn Ops" --steps-file - <<'EOF'
  [{"url": "http://localhost:3004/payments", "text": "El pago #19 dice «Pendiente de aprobación»", "selector": "#row-19"},
   {"url": "http://localhost:3004/payments/19", "text": "El botón Liberar pago (solo super admin)"}]
  EOF
  ide tour show
urls de tu front local (o de un sitio de prueba de [browsers] test_hosts); `selector` (css, opcional) resalta un elemento. Los datos de cada paso
tienen que existir en tu base. Si cambian las pantallas, vuelve a correr `ide tour set`."""),
    "server": ("Servidores de tu desarrollo, por bloque (un bloque por stack de cada repo), igual que el módulo "
               "Servidores. Corren aparte del IDE.", """\
ejemplos:
  ide server ls                             # bloques: PRs, rama, dónde corre, scripts y su estado (y URL)
  ide server start api#4897 build --wait    # espera a que termine; si falla, muestra el log
  ide server start api#4897 run --wait      # espera a que su URL responda (--timeout 300): nada de loops con sleep
  ide server log api#4897 run -n 80
  ide server start admin#98 run             # un front apunta solo a la api de la PR de la que depende
  ide server start embed run --api api#4897 # o a otra (--no-api: la de su .env.local)
  ide server stop api#4897 run
El bloque se nombra por una de sus PRs (api#4897) o por el repo si tiene un solo bloque (admin). Una PR de otra rama
se levanta en un worktree aparte que el IDE crea solo: no cambies la rama de tu worktree para eso.
Si se lo pides al usuario, nombra el bloque por sus PRs: «en Servidores, bloque API #4897: ▶ build y ▶ run».
Fronts: admin llama a la api con VITE_API_URL y embed por el proxy de Vite (VITE_API_PROXY_TARGET), ambos en su
.env.local (lo escribe `point-api <puerto>`; al darle run con --api no hace falta)."""),
    "dep": ("Dependencias entre PRs, además de la sección `## Dependencias` del body (valen las dos).", """\
ejemplos:
  ide dep add api#5101 api#5092 embed#3109  # api#5101 depende de esas
  ide dep rm api#5101 api#5092              # --ignore: ignora también una que está en el body
  ide dep ls api#5101                       # cada una con de dónde sale
Dos PRs que dependen una de la otra van juntas (hotfix y su backport): declara las dos direcciones.
en el body de la PR (sección `## Dependencias` de la plantilla), una por línea:
  finnecto-api#4581 · owner/repo#N · #N (mismo repo) · la URL de la PR
  - «merge en orden: A → B → este PR → C»: solo cuenta lo que va antes de «este PR».
  - Fuera de la sección vale «Depende de finnecto-api#4624» («no depende de …» no cuenta).
  - Una línea que dice que otras PRs «dependen de esta» no cuenta (va al revés). Las casillas [ ]/[x] se ignoran.
  - Para escribirlas: gh pr edit <url> --body-file <archivo> (edita la sección; no borres el resto).
El IDE las muestra (⏸ N pendientes) y avisa al mergear, pero no lo bloquea."""),
    "dev": ("Los desarrollos del tablero.", """\
ejemplos:
  ide dev ls
  ide dev show 12                           # detalle e historial
  ide dev link 12 api#5092                  # asigna PRs a un desarrollo
  ide dev hide 12 [--undo]"""),
    "reply": ("Le escribe al usuario por Telegram (va con «[#n nombre]» adelante). Nunca claves ni datos sensibles.",
              """\
ejemplos:
  ide reply "Listo el filtro de pagos: está en la card de #12"
  ide reply --prompt-file - <<'EOF'
  varias líneas
  EOF
  ide reply --prompt-file attachments/resumen.md   # un archivo de tu carpeta de sesión"""),
    "browser": ("Perfiles de navegador del workspace (uno por cuenta; cada uno es el MCP `browser-<nombre>`). En "
                "localhost no hay un perfil por puerto: `browser-local` entra con la sesión local en todos.", """\
ejemplos:
  ide browser ls                            # perfiles, su url, de qué cuenta son y si tienen sesión
El usuario los crea e inicia sesión (pídele el comando exacto):
  ide browser new aprobador http://localhost:3004 --note "aprobador de Acme"
  ide browser login aprobador
  ide browser login local --url http://localhost:3004
para qué sirve cada uno:
  - browser-local (mcp__browser-local__browser_*): para probar; en localhost entra con la sesión local compartida del
    usuario en cualquier puerto. Si el front te manda al login, pídele `ide browser login local --url <tu front>` (o
    entra con los usuarios de prueba del seed). Nunca un perfil nuevo ni un login por puerto.
  - Otro perfil = otra cuenta a la vez (p.ej. solicitante y aprobador en staging): cada uno es el servidor MCP
    browser-<nombre> (mcp__browser-<nombre>__browser_*) con su cuenta ya iniciada; puedes usar varios a la vez.
    Si falta uno o su sesión expiró, pídele al usuario el comando exacto (new/login): el login lo hace él.
  - Los `local` (localhost y los sitios de [browsers] test_hosts) se usan libremente; los REAL son la cuenta real del usuario.
  - Tamaño de pantalla: browser_resize del MCP (solo cambia esa ventana). Al terminar, browser_close."""),
    "artifact": ("Los artefactos (páginas de claude.ai) del desarrollo: los que publica su claude se suman solos.",
                 "ejemplos:\n  ide artifact ls\n  ide artifact add https://claude.ai/artifact/abc --title \"…\"\n"
                 "  ide artifact rm https://claude.ai/artifact/abc"),
}


class IdeParser(argparse.ArgumentParser):
    """Un error de argumentos dice qué falló y muestra los ejemplos del comando, no solo el usage."""

    def error(self, message: str):  # noqa: D401
        self.print_usage(sys.stderr)
        msg = f"{self.prog}: error: {message}\n"
        if self.epilog:
            msg += "\n" + self.epilog + "\n"
        msg += f"\nmás: {self.prog} --help\n"
        sys.stderr.write(msg)
        sys.exit(2)


def apply(ap: argparse.ArgumentParser, path: str = "") -> None:
    """Pone descripción y ejemplos a cada subcomando (recorre el árbol del parser)."""
    for act in ap._actions:
        if not isinstance(act, argparse._SubParsersAction):
            continue
        helps = {c.dest: c.help for c in act._choices_actions}
        for name, sp in act.choices.items():
            key = f"{path} {name}".strip()
            desc, ex = HELP.get(key, (None, None))
            sp.formatter_class = argparse.RawDescriptionHelpFormatter
            sp.description = desc or sp.description or helps.get(name)
            if ex:
                sp.epilog = ex
            apply(sp, key)
