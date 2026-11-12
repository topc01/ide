// ui/src/modules/notion/TicketsPanel.tsx
/** Módulo Notion: los tickets del desarrollo elegido. Primero el de la sesión, después sus subtickets (las hijas
 *  del ticket en Notion y las sumadas con `ide ticket add-sub`), cada uno con un interruptor para mostrarlo o no en
 *  la card, y al final los de pendientes. Click en uno: lo abre en una tab del IDE. */
import { useState } from "react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import { setSubTicketCard } from "../../transport/folderSessions";
import { openTicketTab, TicketStatus } from "../sessions/DevCard";
import { cn } from "../../lib/utils";

type T = { url: string; status: string | null; title: string | null; card?: boolean };

function Row({ devKey, t, toggle }: { devKey: string; t: T; toggle?: (show: boolean) => void }) {
  return (
    <div className="flex items-start gap-1.5 rounded px-1 py-1 hover:bg-accent/50">
      <button onClick={() => openTicketTab(devKey, t.url, t.title)} title="Abrir la tarjeta en una tab del IDE"
        className="flex min-w-0 flex-1 flex-col items-start gap-0.5 text-left">
        <span className="line-clamp-2 text-xs font-semibold leading-snug">{t.title ?? "(sin leer todavía)"}</span>
        <TicketStatus status={t.status} />
      </button>
      {toggle && (
        <button role="switch" aria-checked={t.card !== false} onClick={() => toggle(t.card === false)}
          title={t.card !== false ? "Se muestra en la card: click para esconderlo ahí (sigue siendo subticket)" : "No se muestra en la card: click para mostrarlo"}
          className={cn("mt-0.5 h-4 w-7 shrink-0 rounded-full border p-[1px] transition-colors",
            t.card !== false ? "border-primary bg-primary/80" : "border-border bg-muted")}>
          <span className={cn("block h-3 w-3 rounded-full bg-background transition-transform", t.card !== false && "translate-x-3")} />
        </button>)}
    </div>);
}

export function TicketsPanel() {
  const dev = useCurrentDev();
  const t = useFolders((s) => (dev ? s.tree.devTickets?.[dev.key] : undefined));
  const [err, setErr] = useState<string | null>(null);
  const head = (x: string) => <div className="mb-1 mt-3 px-1 text-[10px] uppercase tracking-wide text-muted-foreground">{x}</div>;
  if (!dev?.session || dev.session.kind !== "ticket") {
    return <div className="p-3 text-xs text-muted-foreground">Elige un desarrollo con sesión para ver sus tickets de Notion.</div>;
  }
  if (!t?.url) {
    return <div className="p-3 text-xs text-muted-foreground">Este desarrollo no tiene ticket de Notion (se asocia con `ide ticket set`).</div>;
  }
  const sid = dev.session.id;
  const toggle = (u: string) => (show: boolean) => {
    setErr(null);
    setSubTicketCard(getWs(), sid, u, show).catch((e) => setErr(String(e?.message ?? e)));
  };
  const subs = t.subs ?? [];
  return (
    <div className="flex w-full min-w-0 flex-col overflow-y-auto p-2">
      <div className="px-1 text-[10px] uppercase tracking-wide text-muted-foreground">Ticket</div>
      <Row devKey={dev.key} t={{ url: t.url, status: t.status, title: t.title ?? null }} />
      {head(`Subtickets (${subs.length})`)}
      {!subs.length && <div className="px-1 text-xs text-muted-foreground">Ninguno: las hijas del ticket en Notion (relación «Tickets») salen aquí solas.</div>}
      {subs.map((x) => <Row key={x.url} devKey={dev.key} t={x} toggle={toggle(x.url)} />)}
      {t.pending.length > 0 && (<>
        {head(`Pendientes, fuera del desarrollo (${t.pending.length})`)}
        {t.pending.map((x) => <Row key={x.url} devKey={dev.key} t={x} />)}
      </>)}
      {err && <div className="mt-2 px-1 text-xs text-destructive">{err}</div>}
    </div>
  );
}
