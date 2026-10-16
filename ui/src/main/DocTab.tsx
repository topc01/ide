// ui/src/main/DocTab.tsx
import { useEffect, useState } from "react";
import { fetchDoc, onSessionsChanged } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";

/** TICKET.md / REVIEW.md de una sesión (se relee cuando cambia el árbol). */
export function DocTab({ id }: { id: string }) {
  const [text, setText] = useState(""); const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const load = () => fetchDoc(getWs(), id).then((d) => { setText(d.text); setError(null); }).catch((e) => setError(e?.message ?? String(e)));
    load();
    return onSessionsChanged(getWs(), load);
  }, [id]);
  if (error) return <p role="alert" className="p-4 text-xs text-destructive">{error}</p>;
  return <pre className="h-full overflow-auto whitespace-pre-wrap p-4 font-mono text-xs">{text}</pre>;
}
