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
import { ago, STATE, type DevStateInfo, type Phase } from "./devStates";
import { useSidebarConfig } from "../../state/sidebarConfig";
import { openExternal } from "../../lib/openExternal";
import { usePersistentOpen } from "../../lib/persist";
import { notionTab, useDevTabs } from "../../state/devTabs";


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
  approved: "bg-emerald-500/[0.07]", changes: "bg-red-500/[0.07]",
  review: "bg-amber-400/[0.07]", merged: "bg-purple-500/[0.09]",
};
/** Cascarón de las cards de la sidebar (sesiones y PRs): fondo = review; el CI va como marca en la
 *  esquina (CiMark), no en el borde; contorno de acento = seleccionada. */
/** `dev`: estado del desarrollo (Mis desarrollos): el fondo sale de él; si no, de la review (Revisiones). */
export function CardShell({ tone, selected, dashed, onClick, children, dev }:
  { tone: Tone; selected: boolean; dashed?: boolean; onClick?: () => void; children: ReactNode; dev?: DevStateInfo | null }) {
  const bg = dev ? STATE[dev.state][1] : tone.bg && BG[tone.bg];
  return (
    <div data-card onClick={onClick} title={tone.label} aria-current={selected || undefined}
      className={cn("group/card cursor-pointer rounded-md p-[2px] transition-[margin,filter] duration-150 ease-out",
        // inactivas más angostas (se ensanchan en hover); la activa ocupa todo el ancho. El relleno crece lo mismo
        // que la card: el contenido no cambia de ancho (si no, el título y los chips se reacomodaban, la card cambiaba
        // de alto, el mouse quedaba sobre otra card y vibraban)
        selected ? "mx-0" : "mx-2 hover:mx-0 hover:brightness-110",
        dashed ? "" : "bg-border",
        // ring (box-shadow) y no outline: tailwind-merge descartaba `outline` junto a `outline-2`
        selected && "relative ring-2 ring-primary ring-offset-2 ring-offset-card")}>
      {/* seleccionado: barrita de acento a la izquierda, además del contorno */}
      {selected && <span aria-hidden className="absolute -left-[9px] top-1/2 h-7 w-1 -translate-y-1/2 rounded-full bg-primary" />}
      <div className={cn("rounded-[4px] bg-card text-xs", dashed
        && "border-2 border-dashed border-border")}>
        <div className={cn("relative rounded-[4px] px-2 py-1.5 transition-[padding] duration-150 ease-out",
          !selected && "group-hover/card:px-4", bg, dev?.state === "paused" && "opacity-70")}>
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
  const dot = pr?.review ? { approved: "bg-emerald-500", changes: "bg-red-500", review: "bg-amber-400" }[pr.review] : null;
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

/** Acciones de hover: una columna **a la derecha de la card** (fuera de ella, en un portal) con el
 *  ícono y el nombre de cada acción, para no tapar el título. Pegada a la card (sin hueco), con un
 *  margen mínimo para cruzar; al entrar a otra card, la de la anterior se esconde al instante. Siempre existe
 *  (solo se oculta): así una ventana que abrió una acción no se cierra al salir. */
// solo una columna a la vez: al entrar a otra card, la anterior se esconde al instante
let hideCurrent: (() => void) | null = null;

export function CardActions({ children }: { children: ReactNode }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const col = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [shown, setShown] = useState(false);
  const hide = useRef<number | null>(null);
  const keep = () => { if (hide.current) clearTimeout(hide.current); };
  const leave = () => { keep(); hide.current = window.setTimeout(() => setShown(false), 80); };   // solo para cruzar
  useEffect(() => {
    const card = anchor.current?.closest("[data-card]") as HTMLElement | null;
    if (!card) return;
    const measure = () => setRect(card.getBoundingClientRect());
    const off = () => { keep(); setShown(false); };
    const show = () => {
      if (hideCurrent && hideCurrent !== off) hideCurrent();
      hideCurrent = off;
      keep(); measure(); setShown(true); window.setTimeout(measure, 170);   // la card se ensancha al hover
    };
    card.addEventListener("mouseenter", show);
    card.addEventListener("mouseleave", leave);
    measure();
    return () => { card.removeEventListener("mouseenter", show); card.removeEventListener("mouseleave", leave); keep(); };
  }, []);
  // la columna: eventos nativos (el onMouseEnter de React no llega a un portal si se entra desde la card)
  useEffect(() => {
    const el = col.current;
    if (!el) return;
    el.addEventListener("mouseenter", keep);
    el.addEventListener("mouseleave", leave);
    return () => { el.removeEventListener("mouseenter", keep); el.removeEventListener("mouseleave", leave); };
  }, [rect !== null]);
  // el nombre de cada acción: lo corto de su etiqueta (hasta el primer paréntesis)
  useEffect(() => {
    if (!shown) return;
    col.current?.querySelectorAll<HTMLElement>(":scope > button, :scope > a").forEach((el) => {
      const t = el.getAttribute("aria-label") || el.getAttribute("title") || "";
      el.dataset.label = t.split(" (")[0].split(":")[0];
    });
  }, [shown, children]);
  return (<>
    <span ref={anchor} className="hidden" />
    {rect && createPortal(
      <div ref={col} onClick={(e) => e.stopPropagation()}
        style={{ top: rect.top, left: rect.right - 1 }}
        className={cn("fixed z-40 flex min-w-[150px] flex-col gap-0.5 rounded-r-md rounded-bl-md bg-card p-1 shadow-lg ring-1 ring-border transition-opacity",
          "[&>a]:!h-7 [&>a]:!w-full [&>a]:!justify-start [&>a]:gap-2 [&>a]:!px-2 [&>button]:!h-7 [&>button]:!w-full [&>button]:!justify-start [&>button]:gap-2 [&>button]:!px-2",
          "[&>a]:after:text-[11px] [&>a]:after:content-[attr(data-label)] [&>button]:after:text-[11px] [&>button]:after:content-[attr(data-label)]",
          shown ? "opacity-100" : "pointer-events-none opacity-0")}>
        {children}
      </div>, document.body)}
  </>);
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
        onClick={(e) => {
          e.stopPropagation();
          const el = e.currentTarget as HTMLElement;
          setAt(at ? null : (el.closest("[data-card]") ?? el).getBoundingClientRect());   // se abre al lado de la card
        }}>
        <Flag size={11} />
      </QueueItemAction>
      {at && createPortal(<StateMenu dev={dev} devKey={devKey} at={at} onClose={() => setAt(null)} />, document.body)}
    </>);
}

/** Menú para cambiar el estado, a la derecha de la card: arriba lo que hay ahora y de dónde sale; las
 *  tres fases que se ponen a mano; frenarlo (bloqueado pide el motivo) o quitar la pausa; y, plegado,
 *  corregir lo que dice GitHub (la fase puesta gana hasta que GitHub cambie). */
const MANUAL: Phase[] = ["investigating", "developing", "ready-for-review"];
const GITHUB: Phase[] = ["testing", "in-review", "changes-requested", "approved", "merged"];

function sourceOf(dev: DevStateInfo): string {
  if (dev.block) return dev.actor?.startsWith("claude:") ? "lo frenó la sesión" : "lo frenaste tú";
  if (dev.github) return "lo dice GitHub";
  if (dev.inferred) return "deducido de sus PRs";
  if (dev.actor?.startsWith("claude:")) return "lo puso la sesión";
  if (dev.actor === "github") return "lo dice GitHub";
  return "lo pusiste tú";
}

function StateMenu({ dev, devKey, at, onClose }: { dev: DevStateInfo; devKey: string; at: DOMRect; onClose: () => void }) {
  const [blocking, setBlocking] = useState(false);
  const [note, setNote] = useState(dev.block === "blocked" ? dev.note ?? "" : "");
  const [more, setMore] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const W = 260;
  const [pos, setPos] = useState(() => {
    const right = at.right + 8;
    return { top: at.top, left: right + W > window.innerWidth - 8 ? Math.max(8, at.left - W - 8) : right };
  });
  useEffect(() => {
    const out = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) onClose(); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", out); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", out); document.removeEventListener("keydown", esc); };
  }, [onClose]);
  useEffect(() => {                             // que no se salga de la pantalla por abajo
    const h = ref.current?.offsetHeight ?? 0;
    if (pos.top + h > window.innerHeight - 8) setPos((p) => ({ ...p, top: Math.max(8, window.innerHeight - h - 8) }));
  }, [pos.top, more, blocking]);
  const set = (st: string | null, n: string | null = null, gh?: string | null) =>
    setDevState(getWs(), devKey, st, n, gh).then(onClose).catch((e: any) => setErr(e?.message ?? String(e)));
  const [label, , text] = STATE[dev.state];
  const option = (st: Phase, on: boolean) => (
    <button key={st} onClick={() => set(st, null, dev.gh)} title={STATE[st][3]}
      className={cn("flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-accent", on && "bg-accent/70 font-semibold")}>
      <span className={cn("grid h-3 w-3 place-items-center rounded-full border", on ? "border-primary" : "border-muted-foreground")}>
        {on && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}</span>
      <span className={cn(on && STATE[st][2])}>{STATE[st][0]}</span>
    </button>);
  const title = (t: string) => <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t}</div>;
  return (
    <div ref={ref} onClick={(e) => e.stopPropagation()} style={{ top: pos.top, left: pos.left, width: W }}
      className="fixed z-50 max-h-[85vh] overflow-y-auto rounded-md border border-border bg-popover pb-1.5 text-xs text-popover-foreground shadow-xl">
      <div className="border-b border-border px-2 py-2">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Ahora</div>
        <div className={cn("text-sm font-semibold uppercase tracking-wide", text)}>{label}</div>
        <div className="text-[11px] text-muted-foreground">{sourceOf(dev)}{dev.since && !dev.inferred ? ` · hace ${ago(dev.since)}` : ""}</div>
        {dev.note && <div className="mt-0.5 line-clamp-3 text-[11px] italic text-muted-foreground">{dev.note}</div>}
      </div>
      {/* lo puesto a mano tapa lo que dice GitHub: volver a lo automático, a la vista (no escondido abajo) */}
      {dev.manual && dev.gh && !dev.github && dev.manual !== dev.gh && (
        <button onClick={() => set(dev.manual, null)} title="Dejar que la fase la dé GitHub otra vez"
          className="mx-2 mt-2 w-[calc(100%-1rem)] rounded border border-primary/50 px-2 py-1 text-left text-[11px] text-primary hover:bg-accent">
          ↺ volver a lo de GitHub ({STATE[dev.gh][0]})</button>)}
      {title("¿En qué está el trabajo?")}
      {/* «investigando» es solo el estado inicial: pasado eso no se vuelve (el server tampoco lo acepta) */}
      {MANUAL.filter((st) => st !== "investigating" || dev.phase === "investigating").map((st) => option(st, !dev.block && dev.phase === st))}
      {title("¿Está frenado?")}
      {dev.block ? (
        <div className="px-2">
          <button onClick={() => set("unblock")} title={`Vuelve a "${STATE[dev.phase][0]}"`}
            className="w-full rounded border border-border px-2 py-1 text-left hover:bg-accent">✕ Quitar pausa
            <span className="text-muted-foreground"> (vuelve a {STATE[dev.phase][0]})</span></button>
        </div>
      ) : blocking ? (
        <div className="px-2">
          <input autoFocus value={note} onChange={(e) => setNote(e.target.value)} maxLength={300}
            placeholder="¿por qué, o de quién depende?" aria-label="Motivo del bloqueo"
            onKeyDown={(e) => { if (e.key === "Enter" && note.trim()) set("blocked", note.trim()); if (e.key === "Escape") setBlocking(false); }}
            className="w-full rounded border border-border bg-background px-1.5 py-1 text-[11px] outline-none focus:border-primary" />
          <div className="mt-1 flex gap-1">
            <button disabled={!note.trim()} onClick={() => set("blocked", note.trim())} title="Marcar como bloqueado con este motivo"
              className="rounded bg-primary px-2 py-0.5 text-[11px] font-semibold text-primary-foreground disabled:opacity-40">Bloquear</button>
            <button onClick={() => setBlocking(false)} title="No bloquear" className="rounded px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground">Cancelar</button>
          </div>
        </div>
      ) : (
        <div className="flex gap-1 px-2">
          <button onClick={() => setBlocking(true)} title="No se puede avanzar: te pide el motivo"
            className="flex-1 rounded border border-border px-2 py-1 text-red-400 hover:bg-accent">Bloqueado…</button>
          <button onClick={() => set("paused")} title="En espera, sin apuro"
            className="flex-1 rounded border border-border px-2 py-1 text-muted-foreground hover:bg-accent">Pausado</button>
        </div>)}
      <button onClick={() => setMore(!more)} title="Para cuando lo que dice GitHub está mal"
        className="mt-2 flex w-full items-center gap-1 px-2 py-1 text-left text-[11px] text-muted-foreground hover:text-foreground">
        <span className={cn("transition-transform", more && "rotate-90")}>▸</span> Corregir lo que dice GitHub</button>
      {more && (<>
        {GITHUB.map((st) => option(st, !dev.block && dev.phase === st))}
      </>)}
      {err && <p role="alert" className="px-2 py-1 text-[11px] text-destructive">{err}</p>}
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

const REL = {
  ticket: { label: "mismo ticket que", tip: "Tiene el mismo ticket de Notion que el desarrollo" },
  stacked: { label: "apilada sobre", tip: "Una PR suya está apilada sobre una rama del desarrollo" },
  split: { label: "sale del", tip: "El IDE lo separó como línea paralela del desarrollo" },
} as const;

/** Avisos de que el desarrollo cuelga de otro (mismo ticket, apilado sobre su rama, separado de él): si es el
 *  mismo trabajo, se juntan con `ide dev link`. Click: va a ese desarrollo. */
export function RelationChips({ devKey }: { devKey: string }) {
  const rels = useFolders((s) => s.tree.devRelations?.[devKey]);
  if (!rels?.length) return null;
  return (<>{rels.map((r) => {
    const who = r.n != null ? `#${r.n}` : r.dev;
    return (
      <button key={`${r.kind}:${r.dev}`}
        title={`${REL[r.kind].tip} ${who}${r.pr ? ` (${r.pr})` : ""}. Si es el mismo trabajo, júntalos con \`ide dev link\`. Click: ir a ${who}`}
        onClick={(e) => { e.stopPropagation(); useFolders.getState().setActive(r.dev); }}
        className="inline-flex shrink-0 items-center rounded border border-yellow-400/50 px-1 text-[10px] font-semibold text-yellow-300 hover:border-yellow-300">
        {REL[r.kind].label} {who}</button>);
  })}</>);
}

/** El ticket de Notion del desarrollo: chip con su Status (click: abre la tarjeta en Notion) y los tickets de
 *  pendientes; «sin ticket» si no tiene. Solo desarrollos con sesión de ticket. */
export function TicketChip({ devKey }: { devKey: string }) {
  const t = useFolders((s) => s.tree.devTickets?.[devKey]);
  if (!t) return null;
  if (!t.url) return <span title="Este desarrollo no tiene ticket de Notion: la sesión arma el borrador y lo asocia con `ide ticket set`"
    className="inline-flex shrink-0 items-center rounded border border-dashed border-destructive/60 px-1 text-[10px] font-semibold text-destructive">
    sin ticket</span>;
  const subs = (t.subs ?? []).filter((x) => x.card !== false);   // los que el módulo Notion deja en la card
  return (<>
    <TicketBlock devKey={devKey} url={t.url} title={t.title ?? null} status={t.status} error={t.error} what="el ticket" />
    {t.pending.length > 0 && (
      <button title={"Tickets de pendientes (lo que quedó fuera):\n" + t.pending.map((x) => `· ${x.title ?? x.url} (${x.status ?? "?"})`).join("\n")}
        onClick={openTicket(t.pending[0].url)}
        className="inline-flex shrink-0 items-center rounded border border-border px-1 text-[10px] text-foreground hover:border-primary">
        +{t.pending.length} pendiente{t.pending.length > 1 ? "s" : ""}</button>)}
    {subs.length > 0 && <SubTickets devKey={devKey} subs={subs} />}
  </>);
}

// solo links https (el server ya los valida; esto es por si la base trae otra cosa)
const openTicket = (u: string) => (e: React.MouseEvent) => {
  e.stopPropagation();
  try { if (new URL(u).protocol === "https:") openExternal(u); } catch { /* link inválido */ }
};

/** Los colores del Status en la base Desarrollo de Notion (los mismos de Notion). */
const TICKET_COLOR: Record<string, string> = {
  // el color del Status va en el borde y en un fondo muy pálido; la letra, la normal. Solo tonos con versión para el
  // tema claro (index.css: --red-400, --purple-400…)
  "Backlog": "border-red-400/70 bg-red-400/[0.07]", "To Do": "border-purple-400/70 bg-purple-400/[0.07]",
  "In progress": "border-sky-400/70 bg-sky-400/[0.07]", "PR Review": "border-yellow-300/80 bg-yellow-300/[0.08]",
  "Returned": "border-orange-300/80 bg-orange-300/[0.08]", "Live Staging": "border-amber-300/80 bg-amber-300/[0.07]",
  "Completed Staging": "border-emerald-400/70 bg-emerald-400/[0.07]", "Completed Prod": "border-emerald-400/70 bg-emerald-400/[0.07]",
};
const ticketColor = (status: string | null) => (status && TICKET_COLOR[status]) || "border-zinc-300/60 bg-zinc-300/[0.07]";

/** Abre la tarjeta en una tab del desarrollo (la lee el IDE; desde ahí, «Abrir en Notion»). */
export function openTicketTab(devKey: string, url: string, title: string | null) {
  if (devKey.startsWith("s:")) useFolders.getState().setActive(devKey.slice(2));
  useDevTabs.getState().open(devKey, notionTab(url, title));
}

/** El Status de una tarjeta como bloque (el color en el borde y un fondo pálido). */
export function TicketStatus({ status }: { status: string | null }) {
  return <span className={cn("inline-flex items-center rounded border px-1.5 text-[11px] font-semibold text-foreground", ticketColor(status))}>
    {status ?? "sin Status"}</span>;
}

/** Un ticket de Notion: las primeras letras de su título, del color de su Status. Click: lo abre en una tab del IDE. */
function TicketBlock({ devKey, url, title, status, error, what }:
  { devKey: string; url: string; title: string | null; status: string | null; error?: string | null; what: string }) {
  return (
    // sin tooltip (eran demasiadas cosas encima de la card): el color dice el Status; click abre la tarjeta
    <button onClick={(e) => { e.stopPropagation(); openTicketTab(devKey, url, title); }}
      aria-label={`Abrir ${what} en el IDE: ${title ?? url} (${status ?? "?"})${error ? ` ⚠ ${error}` : ""}`}
      className={cn("inline-flex max-w-[10rem] shrink-0 items-center rounded border px-1 text-[10px] font-semibold text-foreground hover:brightness-110",
        error ? "border-destructive/70 bg-destructive/[0.07]" : ticketColor(status))}>
      <span className="truncate">{title ?? status ?? "Notion"}</span></button>);
}

/** Subtickets (las hijas del ticket en Notion y las sumadas con `ide ticket add-sub`): un «◫ N» que los despliega
 *  o esconde (recordado por card), como las PRs mergeadas. */
function SubTickets({ devKey, subs }: { devKey: string; subs: { url: string; status: string | null; title: string | null }[] }) {
  const [show, setShow] = usePersistentOpen(`subtickets.${devKey}`, false);
  return (<>
    <button aria-expanded={show} onClick={(e) => { e.stopPropagation(); setShow(!show); }}
      aria-label={show ? `Esconder los ${subs.length} subtickets` : `Mostrar los ${subs.length} subtickets`}
      className={cn("rounded border px-1 font-mono text-[10px] font-bold text-foreground hover:bg-accent",
        show ? "border-border bg-accent/40" : "border-dashed border-border")}>
      ◫ {subs.length}</button>
    {show && subs.map((x) => <TicketBlock key={x.url} devKey={devKey} url={x.url} title={x.title} status={x.status} what="el subticket" />)}
  </>);
}
