// ui/src/modules/sessions/DevCard.tsx
import type { ReactNode } from "react";
import { Pause } from "lucide-react";
import type { GhPr, MergeJob } from "../../transport/folderSessions";
import { cn } from "../../lib/utils";

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
export function CardShell({ tone, selected, dashed, onClick, children }:
  { tone: Tone; selected: boolean; dashed?: boolean; onClick?: () => void; children: ReactNode }) {
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
        <div className={cn("rounded-[4px] px-2 py-1.5", tone.bg && BG[tone.bg])}>
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
