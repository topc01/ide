// ui/src/modules/sessions/DevCard.tsx
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Clock, Eye, EyeOff, Flag, Pause, Pencil } from "lucide-react";
import { hideDev, renameDev, setDevState, type GhPr, type MergeJob } from "../../transport/folderSessions";
import { QueueItemAction, QueueItemActions } from "../../components/ai-elements/queue";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { cn } from "../../lib/utils";
import { devIndexOf, devKeys, devName, isHidden } from "./desarrollos";
import { useStore } from "../../state/store";
import { ago, PICK_BLOCKS, PHASES, STATE, type DevStateInfo, type State } from "./devStates";
import { useSidebarConfig } from "../../state/sidebarConfig";

/** Estado visual de un desarrollo: el fondo dice la review, el borde el CI / el merge. */
export interface Tone {
  bg: "approved" | "changes" | "review" | "merged" | null;
  blocked: boolean;                 // aprobada pero bloqueada (dependencias o no es la de abajo)
  border: "ci-running" | "ci-failed" | "merging" | null;
  label: string;                    // lo mismo en palabras (tooltip)
}

const MERGE_ACTIVE = ["rebasing", "waiting", "waiting_ci", "merging", "restacking"];

export function devTone(pr?: GhPr, job?: MergeJob, opts: { merged?: boolean; status?: string | null } = {}): Tone {
  const words: string[] = [];
  const merging = !!job && MERGE_ACTIVE.includes(job.state);
  const merged = job?.state === "done" || opts.merged;
  let bg: Tone["bg"] = null;
  const review = pr?.review ?? ({ approved: "approved", "changes-requested": "changes", reviewing: "review" } as
    Record<string, Tone["bg"]>)[opts.status ?? ""] ?? null;
  if (merged || merging) { bg = "merged"; words.push(merging ? "mergeando" : "mergeada"); }
  else if (review) {
    bg = review as Tone["bg"];
    words.push({ approved: "aprobada", changes: "cambios pedidos", review: "esperando revisor" }[review as string] ?? "");
  } else words.push(pr?.draft ? "draft" : "sin review");
  const pending = pr?.depsPending ?? 0;
  const notBottom = !!pr?.stack && pr.stack.position > 1;
  const blocked = bg === "approved" && (pending > 0 || notBottom);
  if (blocked) words.push(pending ? `bloqueada por ${pending} dependencia${pending > 1 ? "s" : ""}` : "bloqueada por su stack");
  let border: Tone["border"] = null;
  if (merging) border = "merging";
  else if (pr?.conflict) { border = "ci-failed"; words.push("conflicto con la base"); }
  else if (pr?.ci === "failure") { border = "ci-failed"; words.push(pr.ciRunning ? "CI falló (sigue corriendo)" : "CI falló"); }
  else if (pr?.ci === "pending") { border = "ci-running"; words.push("CI corriendo"); }
  else if (pr?.ci === "success") words.push("CI ✓");
  if (job?.state === "error") words.push(`error al mergear: ${job.error ?? ""}`);
  return { bg, blocked, border, label: words.filter(Boolean).join(" · ") };
}

const BG: Record<NonNullable<Tone["bg"]>, string> = {
  approved: "bg-emerald-500/[0.07]", changes: "bg-amber-400/[0.07]",
  review: "bg-sky-500/[0.07]", merged: "bg-purple-500/[0.09]",
};
/** Cascarón de las cards de la sidebar (sesiones y PRs): fondo = review; el CI va como marca en la
 *  esquina (CiMark), no en el borde; contorno de acento = seleccionada. */
/** `dev`: estado del desarrollo (Mis desarrollos): el fondo sale de él; si no, de la review (Revisiones). */
export function CardShell({ tone, selected, dashed, onClick, children, dev }:
  { tone: Tone; selected: boolean; dashed?: boolean; onClick?: () => void; children: ReactNode; dev?: DevStateInfo | null }) {
  const bg = dev ? STATE[dev.state][1] : tone.bg && BG[tone.bg];
  return (
    <div onClick={onClick} title={tone.label} aria-current={selected || undefined}
      className={cn("cursor-pointer rounded-md p-[2px] transition-[margin,filter] duration-150 ease-out",
        // inactivas más angostas (se ensanchan en hover); la activa ocupa todo el ancho
        selected ? "mx-0" : "mx-2 hover:mx-0 hover:brightness-110",
        dashed ? "" : "bg-border",
        // ring (box-shadow) y no outline: tailwind-merge descartaba `outline` junto a `outline-2`
        selected && "relative ring-2 ring-primary ring-offset-2 ring-offset-card")}>
      {/* seleccionado: barrita de acento a la izquierda, además del contorno */}
      {selected && <span aria-hidden className="absolute -left-[9px] top-1/2 h-7 w-1 -translate-y-1/2 rounded-full bg-primary" />}
      <div className={cn("rounded-[4px] bg-card text-xs", dashed
        && "border-2 border-dashed border-border")}>
        <div className={cn("relative rounded-[4px] px-2 py-1.5", bg, dev?.state === "paused" && "opacity-70")}>
          {children}
        </div>
      </div>
    </div>
  );
}

/** "finnecto-api" → "API" (el repo tiene que leerse de un vistazo). */
export const repoShort = (repo: string | null | undefined) => (repo ?? "").replace(/^finnecto-/, "").toUpperCase();

/** ⏸ N en la esquina de la card: N dependencias sin mergear (el detalle, en el módulo Dependencias). */
export function DepsPause({ pr }: { pr?: GhPr }) {
  const pending = (pr?.deps ?? []).filter((d) => d.state !== "MERGED" && !d.together);
  if (!pending.length) return null;
  const names = pending.map((d) => `${(d.repo ?? "").replace(/^finnecto-/, "")}#${d.number}`).join(", ");
  return (
    <span title={`Esperando ${pending.length} dependencia${pending.length > 1 ? "s" : ""} sin mergear: ${names}`}
      className="flex shrink-0 items-center gap-0.5 rounded bg-amber-400/15 px-1 font-mono text-[11px] font-bold text-amber-300">
      <Pause size={11} strokeWidth={3} />{pending.length}
    </span>
  );
}

/** Título de la card: el nombre del desarrollo puesto en el IDE o, si no hay, el original (título de
 *  la PR / del ticket). Renombrable con el lápiz (hover) o doble click; Enter guarda, Esc cancela,
 *  vacío vuelve al original (que queda en el tooltip). */
export function DevTitle({ devKey, prs, original, pencil: showPencil = false }:
  { devKey?: string; prs?: GhPr[]; original: string; pencil?: boolean }) {
  const names = useFolders((s) => s.tree.devNames);
  const name = devKey ? devName(names, devKey, prs) : null;
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {                             // "Renombrar" de las acciones de hover de la card
    if (!devKey || showPencil) return;          // el del módulo tiene su lápiz: no escucha a las cards
    const h = (e: Event) => { if ((e as CustomEvent).detail === devKey) { setError(null); setDraft(name ?? original); } };
    window.addEventListener(RENAME_EVENT, h);
    return () => window.removeEventListener(RENAME_EVENT, h);
  }, [devKey, name, original, showPencil]);
  const save = () => {
    if (draft === null || !devKey) return;
    const v = draft.trim();
    setDraft(null);
    if (v === (name ?? original)) return;
    renameDev(getWs(), devKey, v === original ? "" : v).catch((e: any) => setError(e?.message ?? String(e)));
  };
  if (draft !== null) {
    return (
      <input autoFocus value={draft} maxLength={120} aria-label="Nombre del desarrollo"
        onChange={(e) => setDraft(e.target.value)} onClick={(e) => e.stopPropagation()} onBlur={save}
        onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setDraft(null); }}
        className="min-w-0 flex-1 rounded border border-primary bg-background px-1 py-0.5 text-xs font-semibold outline-none" />);
  }
  return (
    <div className="group/title flex min-w-0 flex-1 items-start gap-1">
      <span className="line-clamp-2 min-w-0 text-[13px] font-semibold leading-snug"
        title={name ? `${name}\n(original: ${original})` : original}
        onDoubleClick={devKey ? (e) => { e.stopPropagation(); setDraft(name ?? original); } : undefined}>{name ?? original}</span>
      {error && <span role="alert" title={error} className="text-destructive">⚠</span>}
      {devKey && showPencil && (
        <button aria-label="Renombrar el desarrollo" title="Renombrar el desarrollo (solo en el IDE; vacío = el original)"
          onClick={(e) => { e.stopPropagation(); setError(null); setDraft(name ?? original); }}
          className="mt-0.5 shrink-0 rounded p-0.5 text-muted-foreground opacity-0 hover:text-foreground group-hover/title:opacity-100">
          <Pencil size={10} /></button>)}
    </div>);
}

/** Chip de una PR ("EMBED #2552") o de un repo ("API"), abajo del título de la card. */
/** `pr`: chip de una PR del desarrollo: click la elige (abre su resumen); el punto es su review. */
export function RefChip({ repo, number, title, pr }: { repo: string; number?: number | null; title?: string; pr?: GhPr }) {
  const active = useFolders((s) => !!pr && s.activePrUrl === pr.url);
  const setActivePr = useFolders((s) => s.setActivePr);
  const dot = pr?.review ? { approved: "bg-emerald-500", changes: "bg-amber-400", review: "bg-sky-500" }[pr.review] : null;
  // mergeada: morada con ✓; click la abre en GitHub (ya no está entre las abiertas)
  if (pr?.merged) {
    return <a href={pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
      title={`${pr.repo}#${pr.number}: ${pr.title} (mergeada; click: abrir en GitHub)`}
      className="inline-flex shrink-0 items-center gap-0.5 rounded border border-purple-400/50 px-1 font-mono text-[10px] font-bold tracking-wide text-purple-300 hover:border-purple-300">
      ✓ {repoShort(repo)}{number ? ` #${number}` : ""}</a>;
  }
  const waiting = pr?.review === "approved" ? (pr.reviewers ?? []).filter((r) => r.state === "requested").map((r) => r.login) : [];
  return <span title={title ?? (pr ? `${pr.repo}#${pr.number}: ${pr.title}${waiting.length ? `\naprobada · falta ${waiting.join(", ")}` : ""}` : number ? `${repo}#${number}` : repo)}
    onClick={pr ? (e) => { e.stopPropagation(); setActivePr(pr.url); } : undefined}
    className={cn("inline-flex shrink-0 items-center gap-1 rounded border px-1 font-mono text-[10px] font-bold tracking-wide text-foreground/90",
      active ? "border-primary" : "border-border", pr && "cursor-pointer hover:border-primary/60")}>
    {dot && <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />}
    {repoShort(repo)}{number ? ` #${number}` : ""}</span>;
}

/** Chips de los repos de un desarrollo fullstack ("API · EMBED"). */
export function RepoChips({ repos }: { repos: string[] }) {
  return <span className="flex min-w-0 items-center gap-1 font-mono text-[11px] font-bold tracking-wide">
    {repos.map((r, i) => <span key={r} className="flex items-center gap-1">
      {i > 0 && <span className="font-normal text-muted-foreground">·</span>}{repoShort(r)}</span>)}</span>;
}

/** Ocultar / mostrar un desarrollo en Mis desarrollos (acción de hover de la card). */
export function HideToggle({ devKey, prs }: { devKey: string; prs?: GhPr[] }) {
  const hidden = useFolders((s) => s.tree.devHidden);
  const marked = isHidden(hidden, devKey, prs);
  const label = marked ? "Volver a mostrar en Mis desarrollos" : "Ocultar (pasa al grupo Ocultos de Mis desarrollos)";
  return (
    <QueueItemAction aria-label={label} title={label}
      onClick={(e) => { e.stopPropagation(); hideDev(getWs(), marked ?? devKey, !marked).catch(() => {}); }}>
      {marked ? <Eye size={11} /> : <EyeOff size={11} />}
    </QueueItemAction>);
}

/** Esquina superior derecha de la card: las marcas (⏸ dependencias, CI). El título deja ese lugar libre. */
export function CardCorner({ children }: { children: ReactNode }) {
  return <div className="absolute right-1.5 top-1.5 flex items-center gap-1">{children}</div>;
}

/** Acciones de hover: flotan sobre la esquina (tapan el título y las marcas) y no le quitan ancho al
 *  título cuando no se ven. */
export function CardActions({ children }: { children: ReactNode }) {
  return (
    <QueueItemActions className="pointer-events-none absolute right-1 top-1 z-10 ml-0 rounded-md bg-card px-0.5 shadow-md ring-1 ring-border group-hover/item:pointer-events-auto">
      {children}
    </QueueItemActions>);
}

/** Espacio a la derecha del título para no quedar bajo las marcas de la esquina. */
export const titlePad = (pr?: GhPr) => ((pr?.depsPending ?? 0) > 0 ? "pr-11" : "pr-5");

const RENAME_EVENT = "ide-rename-dev";
/** Acción de hover "Renombrar": abre la edición del título de esa card. */
export function RenameAction({ devKey }: { devKey: string }) {
  return (
    <QueueItemAction aria-label="Renombrar el desarrollo" title="Renombrar el desarrollo (solo en el IDE; vacío = el original)"
      onClick={(e) => { e.stopPropagation(); window.dispatchEvent(new CustomEvent(RENAME_EVENT, { detail: devKey })); }}>
      <Pencil size={11} />
    </QueueItemAction>);
}

/** Chip con el número del desarrollo (#12). */
export function DevIndex({ devKey, prs }: { devKey: string; prs?: GhPr[] }) {
  const index = useFolders((s) => s.tree.devIndex);
  const n = devIndexOf(index, devKey, prs);
  if (n === null) return null;
  return <span title={`desarrollo #${n} (ramas y bases nuevas: d${n}-…)`}
    className="shrink-0 rounded bg-primary/15 px-1 font-mono text-[10px] font-bold text-primary">#{n}</span>;
}

/** Estado del desarrollo en la card: una píldora con su color, cuánto lleva así y la nota de la
 *  sesión en su propia línea. Si Mis desarrollos ya agrupa por estado, el grupo lo dice: solo la nota.
 *  Se cambia con la acción de hover (StateAction). */
export function DevStateLabel({ dev }: { dev: DevStateInfo | null; devKey?: string }) {
  const grouped = useSidebarConfig((s) => (s.groupBy.mine ?? "status") === "status");
  if (!dev) return null;
  const [label, , text] = STATE[dev.state];
  const tip = `Estado del desarrollo: ${label}${dev.block ? ` (fase: ${STATE[dev.phase][0]})` : ""}`
    + `${dev.github ? " · la fase sale de GitHub" : ""}${dev.inferred ? " · deducido de sus PRs" : ""}`
    + `${dev.since ? ` · desde hace ${ago(dev.since)}` : ""}${dev.note ? `\nNota: ${dev.note}` : ""}`;
  return (
    <span className="block basis-full" title={tip}>
      {!grouped && (
        <span className="flex min-w-0 items-center gap-1.5">
          <span className={cn("rounded-sm border border-current px-1.5 text-[10px] font-semibold uppercase tracking-wide",
            dev.inferred ? "text-muted-foreground" : text)}>{label}</span>
          {dev.block && <span className="text-muted-foreground">{STATE[dev.phase][0]}</span>}
          {dev.since && !dev.inferred && <span className="text-muted-foreground">hace {ago(dev.since)}</span>}
        </span>)}
      {dev.outOfDraft && <span className="block text-amber-300"
        title={`Está "${STATE[dev.manual!][0]}" pero una PR ya no está en draft (mientras se trabaja, las PRs van en draft)`}>PR fuera de draft</span>}
      {dev.note && <span className="line-clamp-2 italic text-muted-foreground">{dev.note}</span>}
    </span>);
}

/** Acción de hover "Cambiar estado": abre el menú flotante con todos los estados. */
export function StateAction({ dev, devKey }: { dev: DevStateInfo | null | undefined; devKey?: string }) {
  const [at, setAt] = useState<DOMRect | null>(null);
  if (!dev || !devKey) return null;
  return (
    <>
      <QueueItemAction aria-label="Cambiar el estado" title={`Cambiar el estado (ahora: ${STATE[dev.state][0]})`}
        onClick={(e) => { e.stopPropagation(); setAt(at ? null : (e.currentTarget as HTMLElement).getBoundingClientRect()); }}>
        <Flag size={11} />
      </QueueItemAction>
      {at && createPortal(<StateMenu dev={dev} devKey={devKey} at={at} onClose={() => setAt(null)} />, document.body)}
    </>);
}

/** Menú para cambiar el estado: las fases (cualquiera; la puesta gana hasta que GitHub cambie) y las
 *  pausas (con nota). Flota sobre todo (portal), con fondo sólido. */
function StateMenu({ dev, devKey, at, onClose }: { dev: DevStateInfo; devKey: string; at: DOMRect; onClose: () => void }) {
  const [note, setNote] = useState(dev.note ?? "");
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: at.bottom + 4, left: Math.max(8, at.right - 288) });
  useEffect(() => {
    const out = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) onClose(); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", out); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", out); document.removeEventListener("keydown", esc); };
  }, [onClose]);
  useEffect(() => {                             // que no se salga de la pantalla por abajo
    const h = ref.current?.offsetHeight ?? 0;
    if (pos.top + h > window.innerHeight - 8) setPos((p) => ({ ...p, top: Math.max(8, at.top - h - 4) }));
  }, [at, pos.top]);
  const set = (st: string | null, n: string | null = null, gh?: string | null) =>
    setDevState(getWs(), devKey, st, n, gh).then(onClose).catch((e: any) => setErr(e?.message ?? String(e)));
  const row = (st: State, on: boolean, onClick: () => void, extra?: string) => {
    const [l, bg, t, what] = STATE[st];
    return (
      <button key={st} onClick={onClick} title={on ? `Está así: ${l}` : `Pasar a "${l}"`}
        className={cn("flex w-full items-start gap-2 rounded px-1.5 py-1 text-left hover:bg-accent", on && "bg-accent/70")}>
        <span className={cn("mt-1 h-2 w-2 shrink-0 rounded-full border border-current", bg, t)} />
        <span className="min-w-0 flex-1">
          <span className={cn("block font-semibold", t)}>{l}{extra && <span className="ml-1 font-normal text-muted-foreground">{extra}</span>}</span>
          <span className="block text-[10px] leading-tight text-muted-foreground">{what}</span>
        </span>
        {on && <span className="text-primary">✓</span>}
      </button>);
  };
  return (
    <div ref={ref} onClick={(e) => e.stopPropagation()} style={{ top: pos.top, left: pos.left }}
      className="fixed z-50 max-h-[80vh] w-72 overflow-y-auto rounded-md border border-border bg-popover p-1.5 text-xs text-popover-foreground shadow-xl">
      <div className="px-1.5 pb-0.5 pt-1 text-[10px] uppercase tracking-wide text-muted-foreground">Fase</div>
      {PHASES.map((st) => row(st, dev.phase === st, () => set(st, null, dev.gh),
        dev.gh === st ? "(GitHub)" : undefined))}
      {dev.manual && dev.gh && !dev.github && dev.manual !== dev.gh && (
        <button onClick={() => set(dev.manual, null)} title="Dejar que la fase la dé GitHub otra vez"
          className="w-full rounded px-1.5 py-1 text-left text-muted-foreground hover:bg-accent hover:text-foreground">
          ↺ usar la de GitHub ({STATE[dev.gh][0]})</button>)}
      <div className="px-1.5 pb-0.5 pt-2 text-[10px] uppercase tracking-wide text-muted-foreground">Pausa (tapa la fase)</div>
      <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} aria-label="Nota"
        placeholder="nota: qué falta y de quién"
        onKeyDown={(e) => { if (e.key === "Enter" && dev.block) set(dev.block, note.trim() || null); }}
        className="mx-1.5 mb-1 w-[calc(100%-12px)] rounded border border-border bg-background px-1.5 py-0.5 text-[11px] outline-none focus:border-primary" />
      {PICK_BLOCKS.map((st) => row(st, dev.block === st, () => set(st, note.trim() || null)))}
      {dev.block && (
        <button onClick={() => set("unblock")} title={`Quitar la pausa (vuelve a "${STATE[dev.phase][0]}")`}
          className="w-full rounded px-1.5 py-1 text-left hover:bg-accent">✕ quitar {STATE[dev.block][0]} (vuelve a {STATE[dev.phase][0]})</button>)}
      {err && <p role="alert" className="px-1.5 py-1 text-[11px] text-destructive">{err}</p>}
    </div>);
}

/** Chip "⏱ N": pendientes para después del desarrollo; click abre el módulo Para después. */
export function LaterChip({ devKey, prs }: { devKey: string; prs?: GhPr[] }) {
  const items = useFolders((s) => s.tree.later);
  const { activePanel, setActivePanel, innerSidebarOpen, toggleInnerSidebar } = useStore();
  const keys = devKeys(devKey, prs);
  const n = (items ?? []).filter((it) => keys.includes(it.key)).length;
  if (!n) return null;
  return (
    <button title={`${n} pendiente${n > 1 ? "s" : ""} para después (abre el módulo Para después)`}
      onClick={(e) => { e.stopPropagation(); if (activePanel !== "later") setActivePanel("later"); if (!innerSidebarOpen) toggleInnerSidebar(); }}
      className="inline-flex shrink-0 items-center gap-0.5 rounded border border-yellow-400/40 px-1 font-mono text-[10px] font-bold text-yellow-300 hover:border-yellow-300">
      <Clock size={10} />{n}</button>);
}
