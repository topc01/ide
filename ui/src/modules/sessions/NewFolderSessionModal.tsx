import { useEffect, useState } from "react";
import { useFolders } from "../../state/folders";
import { fetchOpenPrs, newSession, type NewSessionReq, type OpenPr } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Button } from "../../components/ui/button";

const field = "flex flex-col gap-1";
const area = "min-h-[80px] rounded-md border border-border bg-background p-2 text-xs";
const select = "h-8 rounded-md border border-border bg-background px-2 text-xs";

export function NewFolderSessionModal() {
  const { modal, closeModal, setActive } = useFolders();
  const [id, setId] = useState(""); const [title, setTitle] = useState("");
  const [notionUrl, setNotionUrl] = useState(""); const [body, setBody] = useState("");
  const [template, setTemplate] = useState<"ticket" | "none">("ticket");
  const [permissions, setPermissions] = useState<"" | "analyze" | "full" | "default">("");
  const [prUrl, setPrUrl] = useState(""); const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // revisión: repo + una de sus PRs abiertas (o pegar la URL)
  const [openPrs, setOpenPrs] = useState<Record<string, OpenPr[]> | null>(null);
  const [repo, setRepo] = useState("");

  // Un error viejo no debe verse al reabrir el modal.
  useEffect(() => { setError(null); }, [modal]);
  useEffect(() => {
    if (modal !== "review") return;
    setOpenPrs(null); setPrUrl("");
    fetchOpenPrs(getWs()).then((r) => { setOpenPrs(r.repos); setRepo((cur) => cur && r.repos[cur] ? cur : Object.keys(r.repos)[0] ?? ""); })
      .catch((e: any) => setError(e?.message ?? String(e)));
  }, [modal]);

  const payload = (): NewSessionReq => {
    if (modal === "review") return { review: prUrl.trim() };
    const base: NewSessionReq = {};
    if (id.trim()) base.id = id.trim();
    else if (template === "ticket" && notionUrl.trim()) base.notion = notionUrl.trim();
    if (template === "ticket") {
      Object.assign(base, { template: "ticket", title,
        vars: { title, notion_url: notionUrl, body } });
    } else {
      if (title) base.title = title;
      base.prompt = body;
    }
    if (permissions) base.permissions = permissions;
    return base;
  };

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const res: any = await newSession(getWs(), payload());
      setActive(res.session.id);
      closeModal();
    } catch (e: any) { setError(e?.message ?? String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={modal !== null} onOpenChange={(o) => !o && closeModal()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{modal === "review" ? "Nueva revisión de PR" : "Nueva sesión"}</DialogTitle></DialogHeader>
        {modal === "review" ? (
          <div className="flex flex-col gap-2">
            <div className={field}><Label htmlFor="repo">Repo</Label>
              <select id="repo" className={select} value={repo} disabled={!openPrs}
                onChange={(e) => { setRepo(e.target.value); setPrUrl(""); }}>
                {!openPrs && <option>cargando…</option>}
                {openPrs && Object.entries(openPrs).map(([r, list]) => (
                  <option key={r} value={r}>{r.replace(/^finnecto-/, "")} ({list.length} abiertas)</option>))}
              </select></div>
            <div className={field}><Label htmlFor="prsel">PR</Label>
              <select id="prsel" className={select} value={prUrl} disabled={!openPrs?.[repo]?.length}
                onChange={(e) => setPrUrl(e.target.value)}>
                <option value="">elige una PR…</option>
                {(openPrs?.[repo] ?? []).map((p) => (
                  <option key={p.url} value={p.url}>#{p.number} {p.title}{p.author ? ` · @${p.author}` : ""}{p.draft ? " (draft)" : ""}</option>))}
              </select></div>
            <div className={field}><Label htmlFor="pr">o la URL del PR</Label>
              <Input id="pr" placeholder="https://github.com/…/pull/123 (si no aparece arriba)" value={prUrl}
                onChange={(e) => setPrUrl(e.target.value)} /></div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className={field}><Label htmlFor="sid">Id</Label>
              <Input id="sid" placeholder="vacío = el número del desarrollo (#n)" value={id} onChange={(e) => setId(e.target.value)} /></div>
            <div className={field}><Label htmlFor="tpl">Plantilla</Label>
              <select id="tpl" className={select} value={template}
                onChange={(e) => setTemplate(e.target.value as any)}>
                <option value="ticket">ticket</option><option value="none">Sin plantilla</option>
              </select></div>
            <div className={field}><Label htmlFor="title">Título</Label>
              <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
            {template === "ticket" && (
              <div className={field}><Label htmlFor="nurl">URL de Notion</Label>
                <Input id="nurl" value={notionUrl} onChange={(e) => setNotionUrl(e.target.value)} /></div>)}
            <div className={field}><Label htmlFor="body">{template === "ticket" ? "Detalle" : "Prompt"}</Label>
              <textarea id="body" className={area} value={body} onChange={(e) => setBody(e.target.value)} /></div>
            <div className={field}><Label htmlFor="perm">Permisos</Label>
              <select id="perm" className={select} value={permissions}
                onChange={(e) => setPermissions(e.target.value as any)}>
                <option value="">Default del workspace</option>
                <option value="analyze">analyze</option><option value="full">full</option>
                <option value="default">default</option>
              </select></div>
          </div>
        )}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button title="Cerrar sin crear" variant="ghost" onClick={closeModal}>Cancelar</Button>
          <Button title="Crear la sesión y lanzar claude" onClick={submit} disabled={busy || (modal === "review" && !prUrl.trim())}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
