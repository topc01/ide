import { useEffect, useRef, useState } from "react";
import { readTask, saveTask } from "../transport/tasksChannel";
import { getWs } from "../transport/wsClient";
import { useTasks } from "../state/tasks";

type Status = "idle" | "saving" | "saved" | "error";

export function TaskTab({ id }: { id: string }) {
  const taskId = id.slice("task:".length);
  const [title, setTitle] = useState("");
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const reloadRail = useTasks((s) => s.load);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    readTask(getWs(), taskId)
      .then((d) => { if (!cancelled) { setTitle(d.title); setMarkdown(d.markdown); } })
      .catch((e) => { if (!cancelled) setError((e as { message?: string })?.message ?? "desconectado"); });
    return () => { cancelled = true; };
  }, [taskId]);

  function onChange(value: string) {
    setMarkdown(value);
    clearTimeout(timer.current);
    setStatus("saving");
    timer.current = setTimeout(async () => {
      try {
        const meta = await saveTask(getWs(), taskId, value);
        setTitle(meta.title); setStatus("saved");
        reloadRail();
      } catch (e) { setStatus("error"); setError((e as { message?: string })?.message ?? "error"); }
    }, 800);
  }

  if (error && markdown === null) return <div className="p-4 text-sm text-destructive">no se pudo abrir la tarea — {error}</div>;
  if (markdown === null) return <div className="p-4 text-sm text-muted-foreground">cargando…</div>;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-3">
        <span className="text-lg font-bold text-foreground">{title}</span>
        <span className="text-[10px] text-muted-foreground">
          {status === "saving" ? "guardando…" : status === "saved" ? "guardado" : status === "error" ? "error al guardar" : ""}
        </span>
      </div>
      <textarea
        value={markdown}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-0 flex-1 resize-none bg-transparent px-5 py-4 font-mono text-[13px] leading-relaxed text-foreground outline-none"
      />
    </div>
  );
}
