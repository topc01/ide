// ui/src/modules/config/ConfigPanel.tsx
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { usePersistentOpen } from "../../lib/persist";
import { useSidebarConfig, type GroupBy } from "../../state/sidebarConfig";
import { GROUP_LABEL } from "../sessions/GroupedSection";
import { ReviewersPicker, useGithubReviews } from "../sessions/ReviewsSection";
import { cn } from "../../lib/utils";
import { fetchTool, fetchTools, type ToolEntry, type ToolHistory } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { openExternal } from "../../lib/openExternal";

const TOOL_STATE: Record<string, string> = {
  "por-evaluar": "border-border text-muted-foreground", cubierta: "border-sky-400/60 text-sky-300",
  descartada: "border-border text-muted-foreground line-through decoration-1", "a-implementar": "border-amber-400/70 text-amber-300",
  "en-uso": "border-emerald-500/70 text-emerald-300", retirada: "border-violet-400/60 text-violet-300",
};

/** Herramientas evaluadas por la sesión Plugins (`ide tools`): búsqueda, filtro por estado y, al abrir una, su
 *  motivo, link e historial. Solo lectura: las escribe Plugins. */
function ToolsRegistry() {
  const [q, setQ] = useState(""); const [state, setState] = useState("");
  const [items, setItems] = useState<ToolEntry[] | null>(null); const [states, setStates] = useState<string[]>([]);
  const [open, setOpen] = useState<string | null>(null); const [hist, setHist] = useState<ToolHistory[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    const t = window.setTimeout(() => fetchTools(getWs(), q.trim(), state)
      .then((r) => { if (live) { setItems(r.tools); setStates(r.states); setErr(null); } })
      .catch((e) => live && setErr(String(e?.message ?? e))), 200);
    return () => { live = false; window.clearTimeout(t); };
  }, [q, state]);
  useEffect(() => {
    setHist(null);
    if (open) fetchTool(getWs(), open).then((r) => setHist(r.history)).catch(() => setHist([]));
  }, [open]);
  const day = (iso: string) => iso.slice(0, 10);
  return (
    <div className="flex flex-col gap-1.5 text-xs">
      <div className="flex gap-1">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="buscar…" title="Busca en el nombre, el motivo o el link"
          className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-0.5 outline-none focus:border-primary" />
        <select value={state} onChange={(e) => setState(e.target.value)} title="Filtrar por estado"
          className="rounded border border-border bg-background px-1 py-0.5">
          <option value="">todas</option>
          {states.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {err && <div className="text-destructive">{err}</div>}
      {items && !items.length && <div className="text-muted-foreground">ninguna</div>}
      {items?.map((t) => (
        <div key={t.name} className="rounded border border-border">
          <button onClick={() => setOpen(open === t.name ? null : t.name)} title={open === t.name ? "Cerrar el detalle" : "Ver motivo, link e historial"}
            className="flex w-full items-center gap-1.5 px-1.5 py-1 text-left hover:bg-accent/50">
            <span className="min-w-0 flex-1 truncate font-semibold">{t.name}</span>
            <span className={cn("shrink-0 rounded border px-1 text-[10px] leading-4", TOOL_STATE[t.state])}>{t.state}</span>
          </button>
          {open === t.name && (
            <div className="border-t border-border px-1.5 py-1 text-[11px]">
              {t.link && /^https?:\/\//i.test(t.link) && <button onClick={() => openExternal(t.link!)} title="Abrir el link en el navegador"
                className="mb-1 block max-w-full truncate text-left text-primary hover:underline">{t.link}</button>}
              {t.reason && <div className="mb-1 whitespace-pre-wrap text-muted-foreground">{t.reason}</div>}
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">historial</div>
              {!hist && <div className="text-muted-foreground">cargando…</div>}
              {hist?.map((h, i) => (
                <div key={i} className="text-muted-foreground">
                  <span className="text-foreground">{day(h.at)}</span> {h.from ? `${h.from} → ` : ""}{h.to}{h.reason && h.reason !== t.reason ? ` · ${h.reason}` : ""}
                </div>))}
            </div>)}
        </div>))}
    </div>
  );
}

/** Una sección de la configuración: card colapsable (recordada); el ⚙ de esa sección la abre. */
function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  const focus = useSidebarConfig((s) => s.focus);
  const [open, setOpen] = usePersistentOpen(`config.${id}`, true);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focus !== id) return;
    setOpen(true);
    ref.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [focus, id, setOpen]);
  return (
    <div ref={ref} className={cn("mx-1.5 mb-2 overflow-hidden rounded-md border bg-card",
      focus === id ? "border-primary/70" : "border-border")}>
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        title={open ? `Colapsar ${title}` : `Expandir ${title}`}
        className="flex w-full items-center gap-1 px-2 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide hover:bg-accent/50">
        <ChevronRight size={12} className={cn("transition-transform", open && "rotate-90")} />{title}
      </button>
      {open && <div className="border-t border-border px-2 pb-1.5 pt-1">{children}</div>}
    </div>
  );
}

function Choice<T extends string>({ label, value, options, names, onChange }:
  { label: string; value: T; options: T[]; names: Record<string, string>; onChange: (v: T) => void }) {
  return (
    <div className="mb-2">
      <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      {options.map((o) => (
        <label key={o} title={`${label}: ${names[o]}`}
          className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-accent">
          <input type="radio" className="accent-primary" checked={value === o} onChange={() => onChange(o)} />
          {names[o]}
        </label>))}
    </div>
  );
}

/** Módulo Configuración: cómo se ven las secciones de la sidebar (se abre con el ⚙ de cada una). */
export function ConfigPanel() {
  const { groupBy, setGroupBy } = useSidebarConfig();
  const { gh } = useGithubReviews();
  return (
    <div className="flex w-full min-w-0 flex-col overflow-y-auto">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Configuración</div>
      <Block id="reviews" title="Revisiones">
        <Choice<GroupBy> label="Agrupar" value={groupBy.reviews ?? "status"} names={GROUP_LABEL}
          options={["status", "repo", "stack", "author", "none"]} onChange={(g) => setGroupBy("reviews", g)} />
        <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">Revisores visibles (chips)</div>
        <ReviewersPicker gh={gh} />
      </Block>
      <Block id="mine" title="Mis desarrollos">
        <Choice<GroupBy> label="Agrupar" value={groupBy.mine ?? "status"} names={GROUP_LABEL}
          options={["status", "repo", "none"]} onChange={(g) => setGroupBy("mine", g)} />
      </Block>
      <Block id="tools" title="Herramientas evaluadas">
        <ToolsRegistry />
      </Block>
    </div>
  );
}
