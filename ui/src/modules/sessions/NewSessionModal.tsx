import { useEffect, useState } from "react";
import { useSessions } from "../../state/sessions";
import { createSession, fetchTree, fetchBranches, type CreatePayload, type Branch } from "../../transport/sessions";
import { getWs } from "../../transport/wsClient";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Button } from "../../components/ui/button";
import { RadioGroup, RadioGroupItem } from "../../components/ui/radio-group";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";

export function NewSessionModal() {
  const { modalParentId, closeModal, repos, setData } = useSessions();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [role, setRole] = useState("");
  const [kind, setKind] = useState<"coordinator" | "work">("coordinator");
  const [repoId, setRepoId] = useState(repos[0]?.id ?? "");
  const [branchMode, setBranchMode] = useState<"new" | "existing">("new");
  const [newBranch, setNewBranch] = useState("");
  const [existingBranch, setExistingBranch] = useState("");
  const [access, setAccess] = useState<"rw" | "ro">("rw");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (kind === "work" && branchMode === "existing" && repoId) {
      fetchBranches(getWs(), repoId).then(setBranches).catch(() => setBranches([]));
    }
  }, [kind, branchMode, repoId]);

  const open = modalParentId !== undefined;

  const canSubmit = Boolean(name.trim()) && !(kind === "work" && branchMode === "existing" && !existingBranch);

  const submit = async () => {
    const payload: CreatePayload = {
      name, description: description || undefined, role: role || null,
      parentId: modalParentId ?? null, kind,
      ...(kind === "work" ? {
        repoId, access,
        ...(branchMode === "new"
          ? { branch: newBranch || undefined, base: "main" }
          : { branch: existingBranch }),
      } : {}),
    };
    await createSession(getWs(), payload);
    const d = await fetchTree(getWs());
    setData(d.sessions, d.repos);
    closeModal();
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) closeModal(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva sesión</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-session-name">Nombre</Label>
          <Input id="new-session-name" aria-label="Nombre" value={name}
            onChange={(e) => setName(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-session-description">Descripción</Label>
          <Input id="new-session-description" aria-label="Descripción" value={description}
            onChange={(e) => setDescription(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Rol</Label>
          <Select value={role || "__none__"} onValueChange={(v) => setRole(v === "__none__" ? "" : v)}>
            <SelectTrigger aria-label="Rol"><SelectValue placeholder="Sin rol" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Sin rol</SelectItem>
              <SelectItem value="lector">Lector</SelectItem>
              <SelectItem value="revisor">Revisor</SelectItem>
              <SelectItem value="arquitecto">Arquitecto</SelectItem>
              <SelectItem value="disenador">Diseñador</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Tipo</Label>
          <Select value={kind} onValueChange={(v) => setKind(v as "coordinator" | "work")}>
            <SelectTrigger aria-label="Tipo"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="coordinator">Coordinadora (sin branch)</SelectItem>
              <SelectItem value="work">De trabajo (worktree + branch)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {kind === "work" && (
          <>
            <div className="flex flex-col gap-1.5">
              <Label>Repo</Label>
              <Select value={repoId} onValueChange={setRepoId}>
                <SelectTrigger aria-label="Repo"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {repos.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <RadioGroup value={branchMode} onValueChange={(v) => setBranchMode(v as "new" | "existing")}>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="new" id="branch-mode-new" aria-label="Branch nueva" />
                  <Label htmlFor="branch-mode-new">Branch nueva</Label>
                </div>
                {branchMode === "new" && (
                  <Input aria-label="Nombre de branch" placeholder="default = slug del nombre"
                    value={newBranch} onChange={(e) => setNewBranch(e.target.value)} />
                )}
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="existing" id="branch-mode-existing" aria-label="Modo: branch existente" />
                  <Label htmlFor="branch-mode-existing">Usar existente</Label>
                </div>
              </RadioGroup>
              {branchMode === "existing" && (
                <>
                  <Input aria-label="Buscar branch" placeholder="buscar…"
                    value={query} onChange={(e) => setQuery(e.target.value)} />
                  <Select value={existingBranch} onValueChange={setExistingBranch}>
                    <SelectTrigger aria-label="Branch existente"><SelectValue placeholder="Elegir branch" /></SelectTrigger>
                    <SelectContent>
                      {branches.filter((b) => b.name.includes(query)).map((b) => (
                        <SelectItem key={b.name} value={b.name} disabled={b.occupied && access === "rw"}>
                          {b.occupied ? `${b.name} · ocupada` : b.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </>
              )}
              <Select value={access} onValueChange={(v) => setAccess(v as "rw" | "ro")}>
                <SelectTrigger aria-label="Acceso"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="rw">rw (worktree exclusivo)</SelectItem>
                  <SelectItem value="ro">ro (detached, repetible)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={closeModal}>Cancelar</Button>
          <Button onClick={submit} disabled={!canSubmit}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
