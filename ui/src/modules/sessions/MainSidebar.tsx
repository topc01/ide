// ui/src/modules/sessions/MainSidebar.tsx
import { useEffect, useRef, useState } from "react";
import { Plus, Star } from "lucide-react";
import { useFolders } from "../../state/folders";
import { fetchSessions, newSession, onSessionsChanged } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { ConfigButton } from "./GroupedSection";
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
  const tickets = tree.sessions.filter((s) => s.kind !== "main" && s.kind !== "review");
  const reviews = tree.sessions.filter((s) => s.kind === "review");

  return (
    <aside ref={scrollRef} className="flex w-[300px] flex-col overflow-auto border-r border-border bg-card">
      <OffscreenMarker where={offscreen} side="above" container={scrollRef} />
      {!connected && (
        <div role="status" className="bg-destructive/15 px-2.5 py-1 text-[11px] text-destructive">
          desconectado del server: lo de abajo puede estar desactualizado
        </div>
      )}
      <div className={connected ? "" : "opacity-50"}>
        <div className="flex items-center gap-1.5 px-2.5 pb-1 pt-2.5">
          {main ? (
            <button title="Abrir la sesión principal" onClick={() => setActive(main.id)} aria-current={activeId === main.id || undefined}
              className={cn("-my-1 -ml-1.5 flex items-center gap-1.5 rounded border-l-2 border-transparent py-1 pl-1 pr-2 text-xs hover:bg-accent/60",
                activeId === main.id && "border-primary bg-accent")}>
              <Star size={12} className="text-primary" /><span className="font-mono">{main.id}</span>
              <span className="text-muted-foreground">{main.process}</span>
            </button>
          ) : (
            <>
              <button title="Crear y lanzar la sesión principal" onClick={() => { setMainError(null); newSession(getWs(), { main: true })
                  .then((r: any) => setActive(r.session.id))
                  .catch((e: any) => setMainError(e?.message ?? String(e))); }}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                <Star size={12} /> Principal
              </button>
              {mainError && <span role="alert" title={mainError} className="text-xs text-destructive">⚠</span>}
            </>
          )}
          <div className="ml-auto flex items-center gap-1">
            <ConfigButton id="mine" title="Mis desarrollos" />
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
