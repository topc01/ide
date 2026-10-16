// ui/src/modules/sessions/MainSidebar.tsx
import { useEffect, useState } from "react";
import { Plus, Star } from "lucide-react";
import { useFolders } from "../../state/folders";
import { fetchSessions, newSession, onSessionsChanged } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { getGrouper, groupSessions } from "./groupers";
import { GroupMenu } from "./GroupMenu";
import { SessionItem } from "./SessionItem";
import { ReviewsSection } from "./ReviewsSection";
import { MyPrsSection } from "./MyPrsSection";
import { cn } from "../../lib/utils";
import { CustomizationsFooter } from "../settings/CustomizationsFooter";
import { Queue, QueueSection, QueueSectionTrigger, QueueSectionLabel, QueueSectionContent, QueueList }
  from "../../components/ai-elements/queue";

export function MainSidebar() {
  const { tree, connected, groupBy, activeId, setTree, setConnected, setActive, openModal } = useFolders();
  const [mainError, setMainError] = useState<string | null>(null);

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
  const groups = groupSessions(tickets, getGrouper(groupBy));

  return (
    <aside className="flex w-[300px] flex-col overflow-auto border-r border-border bg-card">
      {!connected && (
        <div role="status" className="bg-destructive/15 px-2.5 py-1 text-[11px] text-destructive">
          desconectado del server: lo de abajo puede estar desactualizado
        </div>
      )}
      <div className={connected ? "" : "opacity-50"}>
        <div className="flex items-center gap-1.5 px-2.5 pb-1 pt-2.5">
          {main ? (
            <button onClick={() => setActive(main.id)} aria-current={activeId === main.id || undefined}
              className={cn("-my-1 -ml-1.5 flex items-center gap-1.5 rounded border-l-2 border-transparent py-1 pl-1 pr-2 text-xs hover:bg-accent/60",
                activeId === main.id && "border-primary bg-accent")}>
              <Star size={12} className="text-primary" /><span className="font-mono">{main.id}</span>
              <span className="text-muted-foreground">{main.process}</span>
            </button>
          ) : (
            <>
              <button onClick={() => { setMainError(null); newSession(getWs(), { main: true })
                  .then((r: any) => setActive(r.session.id))
                  .catch((e: any) => setMainError(e?.message ?? String(e))); }}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                <Star size={12} /> Principal
              </button>
              {mainError && <span role="alert" title={mainError} className="text-xs text-destructive">⚠</span>}
            </>
          )}
          <div className="ml-auto flex items-center gap-1">
            <GroupMenu />
            <button aria-label="Nueva sesión" onClick={() => openModal("session")}
              className="text-muted-foreground hover:text-foreground"><Plus size={13} /></button>
          </div>
        </div>

        <Queue>
          {groups.map(({ section, items }) => (
            <QueueSection key={`${groupBy}-${section.id}`} defaultOpen={section.defaultOpen}>
              <QueueSectionTrigger><QueueSectionLabel label={section.label} count={items.length} /></QueueSectionTrigger>
              <QueueSectionContent>
                <QueueList>{items.map((s) => <SessionItem key={s.id} session={s} />)}</QueueList>
              </QueueSectionContent>
            </QueueSection>
          ))}
        </Queue>

        <ReviewsSection sessions={reviews} />
        <MyPrsSection />
      </div>
      <div className="mt-auto"><CustomizationsFooter /></div>
    </aside>
  );
}
