// ui/src/modules/sessions/MainSidebar.tsx
import { useEffect, useRef, useState } from "react";
import { Plus, Gauge, Puzzle, type LucideIcon } from "lucide-react";
import type { FolderSession } from "../../transport/folderSessions";
import { ACTIVITY, activityOf, waitTime } from "./activity";
import { useFolders } from "../../state/folders";
import { fetchSessions, newSession, onSessionsChanged } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { OffscreenMarker, useOffscreenSelected } from "./OffscreenMarker";
import { ReviewsSection } from "./ReviewsSection";
import { MyDevsSection } from "./MyDevsSection";
import { cn } from "../../lib/utils";
import { CustomizationsFooter } from "../settings/CustomizationsFooter";

export function MainSidebar() {
  const { tree, connected, activeId, setTree, setConnected, setActive, openModal } = useFolders();
  const [mainError, setMainError] = useState<string | null>(null);
  const activePrUrl = useFolders((s) => s.activePrUrl);
  const scrollRef = useRef<HTMLElement>(null);
  const offscreen = useOffscreenSelected(scrollRef, `${activeId}|${activePrUrl}`);

  useEffect(() => {
    const ws = getWs();
    fetchSessions(ws).then(setTree).catch(() => setConnected(false));
    const off = onSessionsChanged(ws, setTree);
    ws.onClose(() => setConnected(false));
    return off;
  }, [setTree, setConnected]);

  const main = tree.sessions.find((s) => s.kind === "main");
  const ide = tree.sessions.find((s) => s.kind === "ide");
  const recursos = tree.sessions.find((s) => s.kind === "recursos");
  const plugins = tree.sessions.find((s) => s.kind === "plugins");
  const tickets = tree.sessions.filter((s) => s.kind !== "main" && s.kind !== "review" && s.kind !== "ide" && s.kind !== "recursos" && s.kind !== "plugins");
  const reviews = tree.sessions.filter((s) => s.kind === "review");

  return (
    <aside ref={scrollRef} className="flex w-[300px] flex-col overflow-y-auto overflow-x-hidden [scrollbar-gutter:stable] border-r border-border bg-card">
      <OffscreenMarker where={offscreen} side="above" container={scrollRef} />
      {!connected && (
        <div role="status" className="bg-destructive/15 px-2.5 py-1 text-[11px] text-destructive">
          desconectado del server: lo de abajo puede estar desactualizado
        </div>
      )}
      <div className={connected ? "" : "opacity-50"}>
        {/* pestañas de las sesiones de siempre: la manager, la del IDE, Recursos y Plugins */}
        <div className="flex items-center gap-1.5 px-2.5 pt-2.5">
          {main ? <SessionTab session={main} label="Manager" title={`La sesión manager: coordina los desarrollos (${main.id})`}
              active={activeId === main.id && !activePrUrl} onClick={() => setActive(main.id)} />
            : (<>
              <button title="Crear y lanzar la sesión manager" onClick={() => { setMainError(null); newSession(getWs(), { main: true })
                  .then((r: any) => setActive(r.session.id))
                  .catch((e: any) => setMainError(e?.message ?? String(e))); }}
                className="rounded-md border border-dashed border-border px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground">+ Manager</button>
              {mainError && <span role="alert" title={mainError} className="pb-1.5 text-xs text-destructive">⚠</span>}
            </>)}
          {ide && <SessionTab session={ide} label="IDE" title="Claude en el repo del IDE (para trabajar en el IDE)"
            active={activeId === ide.id && !activePrUrl} onClick={() => setActive(ide.id)} />}
          {recursos && <SessionTab session={recursos} label="Recursos" icon={Gauge}
            title="Claude que mira qué consume el computador (batería, CPU) y corta lo abandonado"
            active={activeId === recursos.id && !activePrUrl} onClick={() => setActive(recursos.id)} />}
          {plugins && <SessionTab session={plugins} label="Plugins" icon={Puzzle}
            title="Claude que evalúa herramientas (plugins, skills, MCP, hooks) y aplica cambios de configuración con tu OK"
            active={activeId === plugins.id && !activePrUrl} onClick={() => setActive(plugins.id)} />}
          <div className="ml-auto">
            <button aria-label="Nueva sesión" title="Nueva sesión" onClick={() => openModal("session")}
              className="grid h-5 w-5 place-items-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"><Plus size={13} /></button>
          </div>
        </div>

        <MyDevsSection tickets={tickets} />

        <ReviewsSection sessions={reviews} />
      </div>
      <OffscreenMarker where={offscreen} side="below" container={scrollRef} />
      <div className="pb-2"><CustomizationsFooter /></div>
    </aside>
  );
}

/** Pestaña de una sesión fija (Manager, IDE): la elegida destacada; el punto es su actividad. */
/** `icon`: una card cuadrada con el ícono en vez del nombre (las de soporte: Recursos, Plugins). */
function SessionTab({ session, label, title, active, onClick, icon: Icon }:
  { session: FolderSession; label: string; title: string; active: boolean; onClick: () => void; icon?: LucideIcon }) {
  const act = activityOf(session);
  const [dot, cls, what] = ACTIVITY[act];
  const note = (waitTime(session) ? ` (terminó a las ${waitTime(session)})` : "")
    + (act === "waiting" && session.activity?.note ? `: ${session.activity.note}` : "")
    + (act === "outdated" && session.activity?.outdated ? ` — después ${session.activity.outdated.what} (${session.activity.outdated.at})` : "");
  return (
    // una card chica (como las de la sidebar): la elegida con el contorno de acento
    <button role="tab" aria-selected={active} aria-label={label} title={`${label}: ${title} — ${what}${note}`} onClick={onClick}
      className={cn("flex items-center gap-1.5 rounded-md border bg-card py-1.5 text-xs font-semibold transition-colors",
        Icon ? "px-2" : "px-3",
        active ? "border-primary text-foreground ring-1 ring-primary"
          : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground")}>
      {Icon ? <Icon aria-hidden className="h-3.5 w-3.5" /> : label}
      <span aria-hidden className={cn("text-[9px]", cls)}>{dot}</span>
    </button>);
}
