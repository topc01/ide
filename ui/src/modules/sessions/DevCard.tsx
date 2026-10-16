// ui/src/modules/sessions/DevCard.tsx
import type { ReactNode } from "react";
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
  approved: "bg-emerald-500/[0.13]", changes: "bg-amber-400/[0.13]",
  review: "bg-sky-500/[0.13]", merged: "bg-purple-500/[0.16]",
};
const STRIPES = "repeating-linear-gradient(135deg, rgba(16,185,129,.20) 0 7px, rgba(16,185,129,.05) 7px 14px)";
const SPIN: Record<string, string> = { "ci-running": "#fbbf24", merging: "#a855f7" };

/** Cascarón de las cards de la sidebar (sesiones y PRs): fondo = review, borde = CI/merge,
 *  contorno claro = seleccionada. */
export function CardShell({ tone, selected, dashed, onClick, children }:
  { tone: Tone; selected: boolean; dashed?: boolean; onClick?: () => void; children: ReactNode }) {
  const spin = tone.border && SPIN[tone.border];
  return (
    <div onClick={onClick} title={tone.label} aria-current={selected || undefined}
      className={cn("cursor-pointer rounded-md p-px",
        !spin && (tone.border === "ci-failed" ? "bg-red-500" : dashed ? "" : "bg-border"),
        selected && "outline outline-2 outline-offset-2 outline-foreground/70")}
      style={spin ? {
        background: `conic-gradient(from var(--spin-angle), ${spin} 0deg, ${spin} 70deg, rgba(255,255,255,.10) 140deg, rgba(255,255,255,.10) 360deg)`,
        animation: "spin-border 2.4s linear infinite",
      } : undefined}>
      <div className={cn("rounded-[5px] bg-card px-2 py-1.5 text-xs", dashed && !spin && tone.border !== "ci-failed"
        && "border border-dashed border-border")}>
        <div className={cn("-m-2 -my-1.5 rounded-[5px] px-2 py-1.5", tone.bg && BG[tone.bg])}
          style={tone.blocked ? { backgroundImage: STRIPES } : undefined}>
          {children}
        </div>
      </div>
    </div>
  );
}

/** "finnecto-api" → "API" (el repo tiene que leerse de un vistazo). */
export const repoShort = (repo: string | null | undefined) => (repo ?? "").replace(/^finnecto-/, "").toUpperCase();

/** Dependencias en palabras: "⛓ espera a api#4592, embed#2512 (+2)" · "⇄ va con api#4602". */
export function DepsLine({ pr }: { pr?: GhPr }) {
  if (!pr?.deps?.length) return null;
  const name = (d: { repo: string | null; number: number | null }) => `${(d.repo ?? "").replace(/^finnecto-/, "")}#${d.number}`;
  const pending = pr.deps.filter((d) => d.state !== "MERGED" && !d.together);
  const together = pr.deps.filter((d) => d.together);
  const list = (xs: typeof pending) => xs.slice(0, 2).map(name).join(", ") + (xs.length > 2 ? ` (+${xs.length - 2})` : "");
  return (<>
    {pending.length > 0 && <span className="text-amber-300" title={`Falta mergear: ${pending.map(name).join(", ")}`}>
      ⛓ espera a {list(pending)}</span>}
    {together.length > 0 && <span className="text-sky-400" title={`Se piden mutuamente: ${together.map(name).join(", ")}`}>
      ⇄ va con {list(together)}</span>}
  </>);
}
