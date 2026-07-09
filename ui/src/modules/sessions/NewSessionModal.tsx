import { useEffect, useState } from "react";
import { useSessions } from "../../state/sessions";
import { createSession, fetchTree, fetchBranches, type CreatePayload, type Branch } from "../../transport/sessions";
import { getWs } from "../../transport/wsClient";

const field: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 3, marginBottom: 10 };
const input: React.CSSProperties = { background: "var(--terminal-bg)", color: "var(--text-primary)",
  border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", fontSize: 12 };

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

  if (modalParentId === undefined) return null;

  const submit = async () => {
    const payload: CreatePayload = {
      name, description: description || undefined, role: role || null,
      parentId: modalParentId, kind,
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
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", display: "grid",
      placeItems: "center", zIndex: 50 }} onClick={closeModal}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 420, background: "var(--panel-bg)",
        border: "1px solid var(--border)", borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: 14, color: "var(--text-primary)", marginBottom: 14 }}>Nueva sesión</div>

        <label style={field}><span style={{ fontSize: 11, color: "var(--text-muted)" }}>Nombre</span>
          <input aria-label="Nombre" style={input} value={name}
            onChange={(e) => setName(e.target.value)} /></label>

        <label style={field}><span style={{ fontSize: 11, color: "var(--text-muted)" }}>Descripción</span>
          <input aria-label="Descripción" style={input} value={description}
            onChange={(e) => setDescription(e.target.value)} /></label>

        <label style={field}><span style={{ fontSize: 11, color: "var(--text-muted)" }}>Rol</span>
          <select aria-label="Rol" style={input} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">Sin rol</option>
            <option value="lector">Lector</option>
            <option value="revisor">Revisor</option>
            <option value="arquitecto">Arquitecto</option>
            <option value="disenador">Diseñador</option>
          </select></label>

        <label style={field}><span style={{ fontSize: 11, color: "var(--text-muted)" }}>Tipo</span>
          <select aria-label="Tipo" style={input} value={kind}
            onChange={(e) => setKind(e.target.value as "coordinator" | "work")}>
            <option value="coordinator">Coordinadora (sin branch)</option>
            <option value="work">De trabajo (worktree + branch)</option>
          </select></label>

        {kind === "work" && (
          <>
            <label style={field}><span style={{ fontSize: 11, color: "var(--text-muted)" }}>Repo</span>
              <select aria-label="Repo" style={input} value={repoId}
                onChange={(e) => setRepoId(e.target.value)}>
                {repos.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select></label>

            <div style={{ ...field, gap: 8 }}>
              <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                <input type="radio" name="bmode" aria-label="Branch nueva"
                  checked={branchMode === "new"} onChange={() => setBranchMode("new")} /> Branch nueva
              </label>
              {branchMode === "new" && (
                <input aria-label="Nombre de branch" style={input} placeholder="default = slug del nombre"
                  value={newBranch} onChange={(e) => setNewBranch(e.target.value)} />
              )}
              <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                <input type="radio" name="bmode" aria-label="Modo: branch existente"
                  checked={branchMode === "existing"} onChange={() => setBranchMode("existing")} /> Usar existente
              </label>
              {branchMode === "existing" && (
                <>
                  <input aria-label="Buscar branch" style={input} placeholder="buscar…"
                    value={query} onChange={(e) => setQuery(e.target.value)} />
                  <select aria-label="Branch existente" size={4} style={input} value={existingBranch}
                    onChange={(e) => setExistingBranch(e.target.value)}>
                    {branches.filter((b) => b.name.includes(query)).map((b) => (
                      <option key={b.name} value={b.name} disabled={b.occupied && access === "rw"}>
                        {b.occupied ? `${b.name} · ocupada` : b.name}
                      </option>
                    ))}
                  </select>
                </>
              )}
              <select aria-label="Acceso" style={input} value={access}
                onChange={(e) => setAccess(e.target.value as "rw" | "ro")}>
                <option value="rw">rw (worktree exclusivo)</option>
                <option value="ro">ro (detached, repetible)</option>
              </select>
            </div>
          </>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
          <button onClick={closeModal} style={{ ...input, cursor: "pointer" }}>Cancelar</button>
          <button onClick={submit} disabled={!name.trim()} style={{
            border: "none", borderRadius: 6, padding: "6px 14px", fontSize: 12,
            cursor: name.trim() ? "pointer" : "not-allowed",
            background: name.trim() ? "var(--accent)" : "var(--border)", color: "var(--on-accent)",
          }}>Crear</button>
        </div>
      </div>
    </div>
  );
}
