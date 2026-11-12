// ui/src/main/NotionTab.tsx
/** Una tarjeta de Notion (el ticket o un subticket del desarrollo) leída en el IDE: título, Status y su contenido.
 *  Solo lectura; «Abrir en Notion» para editarla. Los links a otras tarjetas se abren en otra tab de aquí. */
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ExternalLink, RefreshCw } from "lucide-react";
import { fetchNotionPage } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { openExternal } from "../lib/openExternal";
import { notionTab, useDevTabs } from "../state/devTabs";
import { TicketStatus } from "../modules/sessions/DevCard";

const NOTION_PAGE = /^https:\/\/(?:www\.|app\.)?notion\.(?:so|com)\/(?:[^/?#]+\/)*[^/?#]*[0-9a-f]{32}/i;

export function NotionTab({ devKey, url }: { devKey: string; url: string }) {
  const [page, setPage] = useState<Awaited<ReturnType<typeof fetchNotionPage>> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = useDevTabs((s) => s.open);
  const load = useCallback(() => {
    setBusy(true); setErr(null);
    fetchNotionPage(getWs(), url).then(setPage).catch((e) => setErr(String(e?.message ?? e))).finally(() => setBusy(false));
  }, [url]);
  useEffect(() => { setPage(null); load(); }, [load]);
  const link = (href?: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    if (!href) return;
    if (NOTION_PAGE.test(href.replace(/-/g, ""))) open(devKey, notionTab(href, null));   // otra tarjeta: aquí mismo
    else openExternal(href);
  };
  return (
    <div className="h-full overflow-auto px-6 py-4">
      <div className="mb-3 flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-semibold leading-snug">{page?.title ?? (err ? "No pude leer la tarjeta" : "Cargando…")}</h1>
          {page && <div className="mt-1"><TicketStatus status={page.status} /></div>}
        </div>
        <button title="Volver a leer la tarjeta" onClick={load} disabled={busy}
          className="rounded border border-border p-1 text-muted-foreground hover:text-foreground disabled:opacity-50">
          <RefreshCw size={13} className={busy ? "animate-spin" : ""} /></button>
        <button title="Abrir en Notion (para editarla)" onClick={() => openExternal(page?.notionUrl ?? url)}
          className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:text-foreground">
          <ExternalLink size={12} />Notion</button>
      </div>
      {err && <div className="mb-2 text-xs text-destructive">{err}</div>}
      {page && (page.markdown
        ? <div className="md max-w-3xl"><ReactMarkdown remarkPlugins={[remarkGfm]}
            components={{ a: ({ href, children }) => <a href={href} onClick={link(href)} className="text-primary hover:underline">{children}</a> }}>
            {page.markdown}</ReactMarkdown></div>
        : <div className="text-sm text-muted-foreground">La tarjeta no tiene contenido.</div>)}
    </div>
  );
}
