import { useEffect, useState } from "react";
import { Plus, ListChecks } from "lucide-react";
import { useTasks } from "../../state/tasks";
import { useStore } from "../../state/store";

export function TasksPanel() {
  const { tasks, error, load, create } = useTasks();
  const openTab = useStore((s) => s.openTab);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => { load(); }, [load]);

  function open(id: string, title: string) {
    openTab({ id: `task:${id}`, type: "task", label: title });
  }
  async function submit() {
    if (!name.trim()) return;
    const ref = await create(name.trim());
    setName(""); setAdding(false);
    if (ref) open(ref.id, ref.title);
  }

  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Tareas</span>
        <button onClick={() => setAdding(true)} className="flex items-center gap-1 text-[11px] font-semibold text-[#e0863f]"><Plus size={12} />Nueva</button>
      </div>
      {adding && (
        <input autoFocus placeholder="Nombre de la tarea" value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); if (e.key === "Escape") setAdding(false); }}
          className="mb-2 w-full rounded border border-border bg-background px-2 py-1 font-mono text-[11.5px]" />
      )}
      {error && <div className="px-1 py-2 text-xs text-destructive">desconectado — {error}</div>}
      {tasks.length === 0 && !error && <div className="px-1 py-2 text-xs text-muted-foreground">todavía no hay tareas</div>}
      {tasks.map((t) => (
        <button key={t.id} onClick={() => open(t.id, t.title)}
          className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left hover:bg-accent">
          <ListChecks size={13} className="mt-0.5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12px] font-semibold text-foreground">{t.title}</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-[10px] text-muted-foreground">{t.id}.md</span>
              {t.status && <span className="text-[10px] text-[#e0863f]">{t.status}</span>}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}
