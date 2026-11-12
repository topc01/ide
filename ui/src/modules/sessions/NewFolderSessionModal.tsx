import { useEffect, useState } from "react";
import { useFolders } from "../../state/folders";
import { fetchOpenPrs, newSession, type NewSessionReq, type OpenPr } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Button } from "../../components/ui/button";

const field = "flex min-w-0 flex-col gap-1";
const area = "min-h-[80px] rounded-md border border-border bg-background p-2 text-xs";
const select = "h-8 w-full min-w-0 truncate rounded-md border border-border bg-background px-2 text-xs";

const NOTION_RE = /https?:\/\/(?:www\.|app\.)?notion\.(?:so|com)\/[^\s)>\]]+/i;
const PR_RE = /^\s*(https:\/\/github\.com\/[^/\s]+\/[^/\s]+\/pull\/\d+)\/?\s*$/i;

/** Lo que se crea con el texto del modal: solo el link de una PR = una revisión; con un link de Notion = la sesión
 *  de ese ticket (plantilla `ticket` + lo que escribiste); si no, una sesión que hace lo que dice el texto. */
function fromText(text: string): NewSessionReq {
  const pr = text.match(PR_RE);
  if (pr) return { review: pr[1] };
  const notion = text.match(NOTION_RE)?.[0];
  const rest = notion ? text.replace(notion, "").trim() : text.trim();
  if (notion) return { notion, template: "ticket", title: "", vars: { title: "", notion_url: notion, body: rest },
    ...(rest ? { prompt: rest } : {}) };
  const first = rest.split("\n").find((l) => l.trim())?.trim() ?? "";
  return { title: first.length > 80 ? first.slice(0, 79) + "…" : first, prompt: rest };
}

export function NewFolderSessionModal() {
  const { modal, closeModal, setActive } = useFolders();
  const [body, setBody] = useState("");
  const [more, setMore] = useState(false);
  const [permissions, setPermissions] = useState<"" | "analyze" | "full" | "default">("");
  const [model, setModel] = useState("");
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
    if (modal === "review") return { review: prUrl.trim(), ...(model ? { model } : {}) };
    const base = fromText(body);
    if (permissions && !base.review) base.permissions = permissions;
    if (model) base.model = model;
    return base;
  };

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const res: any = await newSession(getWs(), payload());
      setActive(res.session.id);
      setBody(""); closeModal();
    } catch (e: any) { setError(e?.message ?? String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={modal !== null} onOpenChange={(o) => !o && closeModal()}>
      <DialogContent className="sm:max-w-md [&>*]:min-w-0">
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
            <div className={field}><Label htmlFor="body">¿Qué tiene que hacer?</Label>
              <textarea id="body" autoFocus className={area + " min-h-[140px]"} value={body} onChange={(e) => setBody(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && body.trim() && !busy) { e.preventDefault(); submit(); } }}
                placeholder={"El prompt inicial. Con el link de un ticket de Notion, queda asociada a ese ticket; solo el link de una PR, es una revisión.\n⌘Enter crea."} /></div>
            <button type="button" onClick={() => setMore((m) => !m)} title="Permisos y modelo de la sesión (si no, los de siempre)"
              className="self-start text-[11px] text-muted-foreground hover:text-foreground">{more ? "▾" : "▸"} más opciones</button>
            {more && (<>
              <div className={field}><Label htmlFor="perm">Permisos</Label>
                <select id="perm" className={select} value={permissions}
                  onChange={(e) => setPermissions(e.target.value as any)}>
                  <option value="">Default del workspace</option>
                  <option value="analyze">analyze</option><option value="full">full</option>
                  <option value="default">default</option>
                </select></div>
              <div className={field}><Label htmlFor="model">Modelo</Label>
                <select id="model" className={select} value={model} title="El modelo de claude de la sesión (se mantiene al retomarla)"
                  onChange={(e) => setModel(e.target.value)}>
                  <option value="">El de siempre</option>
                  <option value="opus">opus</option><option value="sonnet">sonnet (más barato)</option>
                  <option value="haiku">haiku (el más barato, para lo muy simple)</option>
                </select></div>
            </>)}
          </div>
        )}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button title="Cerrar sin crear" variant="ghost" onClick={closeModal}>Cancelar</Button>
          <Button title="Crear la sesión y lanzar claude" onClick={submit} disabled={busy || (modal === "review" ? !prUrl.trim() : !body.trim())}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
