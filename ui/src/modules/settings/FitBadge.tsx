import { useState } from "react";
import type { FitInfo } from "../../state/models";

const LABEL: Record<string, string> = { ok: "entra", tight: "justo", no: "no entra" };

function levelProps(level: string): { className: string; style?: React.CSSProperties } {
  if (level === "no") return { className: "font-medium text-destructive" };
  if (level === "tight") return { className: "font-medium", style: { color: "#e0863f" } };
  return { className: "font-medium", style: { color: "#7fb069" } };
}

export function FitBadge({ fit }: { fit?: FitInfo | null }) {
  const [open, setOpen] = useState(false);
  if (!fit) return null;
  const lp = levelProps(fit.level);
  const sc = fit.scoreComponents;
  return (
    <div className="mt-1 text-[10px]">
      <div className="flex items-center gap-2">
        <span data-fit={fit.level} className={lp.className} style={lp.style}>{LABEL[fit.level]}</span>
        <span className="text-muted-foreground">{fit.estimatedTps} tok/s</span>
        <button title="Ver por qué entra (o no) en esta máquina" data-fit-details onClick={() => setOpen((o) => !o)}
          className="text-muted-foreground hover:text-foreground">detalles</button>
      </div>
      {open && (
        <div data-fit-detail className="mt-1 flex flex-col gap-0.5 text-muted-foreground">
          <span>RAM: {fit.memoryRequiredGb} GB de {fit.memoryAvailableGb} GB</span>
          <span>Disco: {fit.diskSizeGb} GB · quant: {fit.bestQuant}</span>
          <span>Contexto: {fit.contextLength}</span>
          <span>Score {fit.score} — fit {sc.fit} · velocidad {sc.speed} · calidad {sc.quality} · contexto {sc.context}</span>
        </div>
      )}
    </div>
  );
}
