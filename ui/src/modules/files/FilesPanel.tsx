import { useEffect, useState } from "react";
import { Folder, File as FileIcon } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";
import { listFiles, openFile, type FileEntry } from "../../transport/filesChannel";
import { getWs } from "../../transport/wsClient";

const join = (base: string, name: string) => (base ? `${base}/${name}` : name);

function TreeNode({ sessionId, path, entry, depth }:
  { sessionId: string; path: string; entry: FileEntry; depth: number }) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<FileEntry[] | null>(null);
  const full = join(path, entry.name);
  const onClick = () => {
    if (entry.type === "file") {
      const key = `${sessionId}:${full}`;
      const st = useStore.getState();
      const existing = st.fileTabs[key];
      if (existing && st.openTabs.some((t) => t.id === existing)) {
        st.setActiveTab(existing);           // ya abierto → enfocar, no reabrir vim
        return;
      }
      openFile(getWs(), sessionId, full)
        .then(({ id }) => {
          const s2 = useStore.getState();
          s2.openTab({ id, type: "terminal", label: entry.name });
          s2.noteFileTab(key, id);
        })
        .catch(() => {});
      return;
    }
    const next = !open;
    setOpen(next);
    if (next && children === null)
      listFiles(getWs(), sessionId, full).then((r) => setChildren(r.entries)).catch(() => setChildren([]));
  };
  return (
    <div>
      <button data-file-node={full} onClick={onClick} style={{ paddingLeft: depth * 12 + 10 }}
        className="flex w-full items-center gap-1.5 py-0.5 text-xs text-foreground hover:bg-accent">
        {entry.type === "dir" ? <Folder size={12} className="text-muted-foreground" />
          : <FileIcon size={12} className="text-muted-foreground" />}
        <span>{entry.name}</span>
      </button>
      {open && children && children.map((c) => (
        <TreeNode key={c.name} sessionId={sessionId} path={full} entry={c} depth={depth + 1} />
      ))}
    </div>
  );
}

export function FilesPanel() {
  const sessionId = useSessions((s) => s.activeSessionId);
  const [roots, setRoots] = useState<FileEntry[] | null>(null);
  useEffect(() => {
    if (!sessionId) { setRoots(null); return; }
    listFiles(getWs(), sessionId, "").then((r) => setRoots(r.entries)).catch(() => setRoots([]));
  }, [sessionId]);
  return (
    <aside className="w-64 overflow-auto border-r border-border bg-card">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Archivos</div>
      {!sessionId ? (
        <div className="mx-2.5 text-[11px] text-muted-foreground">Seleccioná una sesión para ver sus archivos.</div>
      ) : (
        <div className="flex flex-col" key={sessionId}>
          {roots?.map((e) => <TreeNode key={e.name} sessionId={sessionId} path="" entry={e} depth={0} />)}
        </div>
      )}
    </aside>
  );
}
