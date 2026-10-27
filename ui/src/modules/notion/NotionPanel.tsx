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
          onKeyDown={(e) => { if (e.key === "Enter" && token) { connect(token); setToken(""); } }}
          className="mb-2 w-full rounded border border-border bg-background px-2 py-1 font-mono text-[11.5px]" />
        <button title="Conectar Notion con este token" onClick={() => { if (token) { connect(token); setToken(""); } }} disabled={!token}
          className="mb-2 rounded bg-primary px-3 py-1 text-[11.5px] font-semibold text-primary-foreground disabled:opacity-50">
          Conectar
        </button>
        {error && <div className="mb-2 text-xs text-destructive">{error}</div>}
        <div className="text-[11px] leading-relaxed text-muted-foreground">
          Crea una integración interna en{" "}
          <a href="https://www.notion.so/my-integrations" target="_blank" rel="noreferrer" className="text-primary">notion.so/my-integrations</a>,
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
          <button aria-label="desconectar" title="desconectar" onClick={() => disconnect()} className="text-muted-foreground hover:text-foreground"><LogOut size={13} /></button>
          <button aria-label="refrescar" title="refrescar" onClick={() => load()} className="text-muted-foreground hover:text-foreground"><RefreshCw size={13} /></button>
          <button title="Agregar una página de Notion" onClick={() => setAdding(true)} className="flex items-center gap-1 text-[11px] font-semibold text-primary"><Plus size={12} />Nueva</button>
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
        <button title="Abrir esta página" key={p.id} onClick={() => openTab({ id: `notion:${p.id}`, type: "page", label: p.title })}
          className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left hover:bg-accent">
          <FileText size={13} className="mt-0.5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-foreground">{p.title}</span>
        </button>
      ))}
    </div>
  );
}
