// ui/src/modules/sessions/DevCard.tsx
import type { ReactNode } from "react";
import type { GhPr, MergeJob } from "../../transport/folderSessions";
import { cn } from "../../lib/utils";

/** Estado visual de un desarrollo: el fondo dice la review, el borde el CI / el merge. */
export interface Tone {
  bg: "approved" | "changes" | "review" | "merged" | null;
  blocked: boolean;                 // aprobada pero bloqueada (dependencias o no es la de abajo)
  border: "ci-running" | "ci-failed" | "merging" | "blocked" | null;
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
  if (!border && blocked) border = "blocked";
  if (job?.state === "error") words.push(`error al mergear: ${job.error ?? ""}`);
  return { bg, blocked, border, label: words.filter(Boolean).join(" · ") };
}

const BG: Record<NonNullable<Tone["bg"]>, string> = {
  approved: "bg-emerald-500/[0.07]", changes: "bg-amber-400/[0.07]",
  review: "bg-sky-500/[0.07]", merged: "bg-purple-500/[0.09]",
};
const SPIN: Record<string, string> = { "ci-running": "#fbbf24", merging: "#a855f7" };
// bordes fijos (2 px): rojo CI falló; café bloqueada (no se confunde con el amarillo de cambios
// pedidos, que es de fondo, ni con el amarillo que gira del CI corriendo)
const FIXED: Record<string, string> = { "ci-failed": "bg-red-500", blocked: "bg-[#a0522d]" };

/** Cascarón de las cards de la sidebar (sesiones y PRs): fondo = review, borde = CI/merge,
 *  contorno claro = seleccionada. */
export function CardShell({ tone, selected, dashed, onClick, children }:
  { tone: Tone; selected: boolean; dashed?: boolean; onClick?: () => void; children: ReactNode }) {
  const spin = tone.border && SPIN[tone.border];
  return (
    <div onClick={onClick} title={tone.label} aria-current={selected || undefined}
      className={cn("cursor-pointer rounded-md p-[2px]",
        !spin && (tone.border ? FIXED[tone.border] : dashed ? "" : "bg-border"),
        // ring (box-shadow) y no outline: tailwind-merge descartaba `outline` junto a `outline-2`
        selected && "relative ring-2 ring-primary ring-offset-2 ring-offset-card")}
      style={spin ? {
        background: `conic-gradient(from var(--spin-angle), ${spin} 0deg, ${spin} 70deg, rgba(255,255,255,.10) 140deg, rgba(255,255,255,.10) 360deg)`,
        animation: "spin-border 2.4s linear infinite",
      } : undefined}>
      {/* seleccionado: barrita de acento a la izquierda, además del contorno */}
      {selected && <span aria-hidden className="absolute -left-[9px] top-1/2 h-7 w-1 -translate-y-1/2 rounded-full bg-primary" />}
      <div className={cn("rounded-[4px] bg-card text-xs", dashed && !spin && !tone.border
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

/** Dependencias pendientes como "N dependencias" (el detalle está en el módulo Dependencias). */
export function DepsLine({ pr }: { pr?: GhPr }) {
  const n = pr?.depsPending ?? 0;
  if (!n) return null;
  return <span className="text-amber-300" title="Falta mergear estas PRs antes: ver el módulo Dependencias">
    {n} dependencia{n > 1 ? "s" : ""}</span>;
}
