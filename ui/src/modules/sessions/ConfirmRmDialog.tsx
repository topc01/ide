// ui/src/modules/sessions/ConfirmRmDialog.tsx
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { rmSession } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";

export function ConfirmRmDialog({ id, open, onClose }: { id: string; open: boolean; onClose: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [needsForce, setNeedsForce] = useState(false);
  useEffect(() => { if (open) { setError(null); setNeedsForce(false); } }, [open]);
  const run = async (force: boolean) => {
    try { await rmSession(getWs(), id, force); onClose(); }
    catch (e: any) {
      setError(e?.message ?? String(e));
      setNeedsForce(e?.code === "uncommitted_changes");
    }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Borrar sesión {id}</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">
          Para el proceso, corre <code>archive</code> de cada repo, quita los worktrees y borra la carpeta.
          Las branches se conservan.
        </p>
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          {needsForce
            ? <Button variant="destructive" onClick={() => run(true)}>Borrar igual (--force)</Button>
            : <Button variant="destructive" onClick={() => run(false)}>Borrar</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
