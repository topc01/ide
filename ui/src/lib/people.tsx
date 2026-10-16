// ui/src/lib/people.tsx
import type { CSSProperties, ReactNode } from "react";

/** Color fijo por persona (mismo login → mismo color en toda la app). */
export function personStyle(login: string): CSSProperties {
  let h = 0;
  for (const c of login.toLowerCase().replace(/^@/, "")) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const hue = (h * 137) % 360;               // salto áureo: logins parecidos, colores distintos
  return { color: `hsl(${hue} 75% 72%)`, borderColor: `hsl(${hue} 60% 55% / .55)`,
           background: `hsl(${hue} 60% 50% / .12)` };
}

/** Chip de una persona (autor, revisor, conteo de revisiones). */
export function PersonChip({ login, children, title, strong }:
  { login: string; children?: ReactNode; title?: string; strong?: boolean }) {
  const name = login.replace(/^@/, "");
  return (
    <span title={title ?? name} style={personStyle(name)}
      className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-px font-mono text-[10px] leading-4 transition-[filter] hover:brightness-125 ${strong ? "font-bold" : ""}`}>
      {name}{children}
    </span>
  );
}
