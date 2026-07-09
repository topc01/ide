import { useState } from "react";
import { useSessions } from "../../state/sessions";
import { createSession, fetchTree, type CreatePayload } from "../../transport/sessions";
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

  if (modalParentId === undefined) return null;

  const submit = async () => {
    const payload: CreatePayload = {
      name, description: description || undefined, role: role || null,
      parentId: modalParentId, kind,
      ...(kind === "work" ? { repoId, access: "rw" } : {}),
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
          <label style={field}><span style={{ fontSize: 11, color: "var(--text-muted)" }}>Repo</span>
            <select aria-label="Repo" style={input} value={repoId}
              onChange={(e) => setRepoId(e.target.value)}>
              {repos.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select></label>
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
