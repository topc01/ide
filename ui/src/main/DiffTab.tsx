import { useEffect, useState } from "react";
import { fetchDiff, type DiffLine, type DiffLineType } from "../transport/changesChannel";
import { getWs } from "../transport/wsClient";

const STYLE: Record<DiffLineType, { bg: string; color: string }> = {
  add: { bg: "rgba(127,176,105,0.14)", color: "var(--diff-add)" },
  del: { bg: "rgba(201,106,78,0.14)", color: "var(--diff-del)" },
  hunk: { bg: "transparent", color: "var(--primary)" },
  ctx: { bg: "transparent", color: "var(--diff-ctx)" },
};

// id = "diff:<sessionId>:<status>:<path>"; path puede contener ":".
// Si el slot de status arranca con "@" es un diff de commit: status="" y sha=<resto>.
function parseId(id: string): { sessionId: string | null; status: string; sha?: string; path: string } {
  const rest = id.slice("diff:".length);
  const i1 = rest.indexOf(":");
  const i2 = rest.indexOf(":", i1 + 1);
  const slot = rest.slice(i1 + 1, i2);
  const isCommit = slot.startsWith("@");
  return {
    sessionId: rest.slice(0, i1) || null,
    status: isCommit ? "" : slot,
    sha: isCommit ? slot.slice(1) : undefined,
    path: rest.slice(i2 + 1),
  };
}

export function DiffTab({ id }: { id: string }) {
  const { sessionId, status, sha, path } = parseId(id);
  const [lines, setLines] = useState<DiffLine[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ls = await fetchDiff(getWs(), { sessionId, path, status, sha });
        if (!cancelled) { setLines(ls); setError(null); }
      } catch (e: unknown) {
        if (!cancelled) setError((e as { message?: string })?.message ?? "desconectado");
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  if (error) {
    return <div className="p-4 text-sm text-destructive">no se pudo leer el diff — {error}</div>;
  }
  return (
    <div className="h-full overflow-auto py-4">
      <div className="px-5 pb-3 font-mono text-xs text-muted-foreground">{path}</div>
      {lines.map((l, i) => (
        <div key={i} className="whitespace-pre px-5 font-mono text-[12.5px] leading-relaxed"
          style={{ background: STYLE[l.type].bg, color: STYLE[l.type].color }}>
          {l.text || " "}
        </div>
      ))}
    </div>
  );
}
