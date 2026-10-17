// ui/src/modules/sessions/DevCard.tsx
import { useEffect, useState, type ReactNode } from "react";
import { Eye, EyeOff, Pause, Pencil } from "lucide-react";
import { hideDev, renameDev, type GhPr, type MergeJob } from "../../transport/folderSessions";
import { QueueItemAction, QueueItemActions } from "../../components/ai-elements/queue";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { cn } from "../../lib/utils";
import { devIndexOf, devName, isHidden } from "./desarrollos";
import { ago, STATE, type DevStateInfo } from "./devStates";

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
  else if (pr?.ci === "failure") { border = "ci-failed"; words.push(pr.conflict ? "conflicto con la base" : "CI falló"); }
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
  return <span title={title ?? (pr ? `${pr.repo}#${pr.number}: ${pr.title}` : number ? `${repo}#${number}` : repo)}
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

/** Estado en palabras: "bloqueado por el cliente · en revisión · 3 d · nota". Si el desarrollo sigue
 *  activo (puesto a mano) pero una PR ya salió de draft, lo dice. */
export function DevStateLabel({ dev }: { dev: DevStateInfo | null }) {
  if (!dev) return null;
  const [label, , text] = STATE[dev.state];
  const parts = [label, ...(dev.block ? [STATE[dev.phase][0]] : []), ...(dev.since && !dev.inferred ? [ago(dev.since)] : [])];
  const tip = `${label}${dev.block ? ` (fase: ${STATE[dev.phase][0]})` : ""}${dev.github ? " · fase según GitHub" : ""}`
    + `${dev.inferred ? " · inferido: cámbialo en el módulo Desarrollo" : ""}${dev.since ? ` · desde hace ${ago(dev.since)}` : ""}`
    + `${dev.note ? ` — ${dev.note}` : ""}`;
  return (<>
    <span title={tip} className={cn("min-w-0 truncate", dev.inferred ? "text-muted-foreground" : text)}>
      {parts.join(" · ")}{dev.note ? ` · ${dev.note}` : ""}</span>
    {dev.outOfDraft && <span className="text-amber-300"
      title={`Está "${STATE[dev.manual!][0]}" pero una PR ya no está en draft (mientras se trabaja, las PRs van en draft)`}>PR fuera de draft</span>}
  </>);
}
