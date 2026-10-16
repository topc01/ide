// ui/src/modules/config/ConfigPanel.tsx
import { useEffect, useRef, type ReactNode } from "react";
import { useSidebarConfig, type GroupBy } from "../../state/sidebarConfig";
import { GROUP_LABEL } from "../sessions/GroupedSection";
import { ReviewersPicker, useGithubReviews } from "../sessions/ReviewsSection";
import { cn } from "../../lib/utils";

function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  const focus = useSidebarConfig((s) => s.focus);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (focus === id) ref.current?.scrollIntoView({ block: "start", behavior: "smooth" }); }, [focus, id]);
  return (
    <div ref={ref} className={cn("mx-1.5 mb-2 rounded-md border border-transparent p-1.5", focus === id && "border-primary/70")}>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide">{title}</div>
      {children}
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
          options={["status", "repo", "none"]} onChange={(g) => setGroupBy("mine", g)} />
      </Block>
    </div>
  );
}
