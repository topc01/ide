// ui/src/modules/sessions/ConfirmArchiveDialog.tsx
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { archiveSession } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";

export function ConfirmArchiveDialog({ id, open, onClose }: { id: string; open: boolean; onClose: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [needsForce, setNeedsForce] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setError(null); setNeedsForce(false); } }, [open]);
  const run = async (force: boolean) => {
    setBusy(true);
    try { await archiveSession(getWs(), id, force); onClose(); }
    catch (e: any) {
      setError(e?.message ?? String(e));
      setNeedsForce(e?.code === "archive_failed");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Archivar sesión {id}</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">
          Para el proceso, corre <code>archive</code> de cada repo, deja cada worktree en detach (la
          rama queda libre; los cambios sin commitear se conservan), borra los archivos ignorados y
          mueve todo a <code>.ide/archive/</code>. No se puede deshacer desde la UI.
        </p>
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          {needsForce
            ? <Button variant="destructive" disabled={busy} onClick={() => run(true)}>Archivar igual</Button>
            : <Button variant="destructive" disabled={busy} onClick={() => run(false)}>{busy ? "Archivando…" : "Archivar"}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
