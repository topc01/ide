// ui/src/modules/config/ConfigPanel.tsx
import { useEffect, useRef, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { usePersistentOpen } from "../../lib/persist";
import { useSidebarConfig, type ColorBy, type GroupBy } from "../../state/sidebarConfig";
import { GROUP_LABEL } from "../sessions/GroupedSection";
import { ReviewersPicker, useGithubReviews } from "../sessions/ReviewsSection";
import { cn } from "../../lib/utils";

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
  const { groupBy, setGroupBy, colorBy, setColorBy } = useSidebarConfig();
  const { gh } = useGithubReviews();
  return (
    <div className="flex w-full min-w-0 flex-col overflow-hidden">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Configuración</div>
      <Block id="reviews" title="Revisiones">
        <Choice<GroupBy> label="Agrupar" value={groupBy.reviews ?? "status"} names={GROUP_LABEL}
          options={["status", "repo", "stack", "author", "none"]} onChange={(g) => setGroupBy("reviews", g)} />
        <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">Revisores visibles (chips)</div>
        <ReviewersPicker gh={gh} />
      </Block>
      <Block id="mine" title="Mis desarrollos">
        <Choice<GroupBy> label="Agrupar" value={groupBy.mine ?? "status"} names={GROUP_LABEL}
          options={["status", "devstate", "repo", "none"]} onChange={(g) => setGroupBy("mine", g)} />
        {/* el color sigue a la dimensión que agrupa; solo se elige si se agrupa por otra cosa */}
        {!["status", "devstate"].includes(groupBy.mine ?? "status") ? (
          <Choice<ColorBy> label="Color de las cards" value={colorBy.mine ?? "pr"}
            names={{ pr: "Estado de la PR", dev: "Estado del desarrollo" }}
            options={["pr", "dev"]} onChange={(c) => setColorBy("mine", c)} />
        ) : (
          <p className="mb-2 text-[11px] text-muted-foreground">
            Color de las cards: el de la agrupación ({(groupBy.mine ?? "status") === "status" ? "estado de la PR" : "estado del desarrollo"}).</p>)}
      </Block>
    </div>
  );
}
