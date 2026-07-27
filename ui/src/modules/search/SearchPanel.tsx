import { useStore } from "../../state/store";
import { useSessions } from "../../state/sessions";
import { getWs } from "../../transport/wsClient";
import { searchContent } from "../../transport/searchChannel";
import { openFile } from "../../transport/filesChannel";

function Highlighted({ text, ranges }: { text: string; ranges: [number, number][] }) {
  if (!ranges.length) return <>{text}</>;
  const out: React.ReactNode[] = []; let i = 0;
  ranges.forEach(([s, e], k) => {
    if (s > i) out.push(text.slice(i, s));
    out.push(<mark key={k} className="bg-primary/30 text-foreground">{text.slice(s, e)}</mark>);
    i = e;
  });
  if (i < text.length) out.push(text.slice(i));
  return <>{out}</>;
}

export function SearchPanel() {
  const sid = useSessions((s) => s.activeSessionId);
  const { searchQuery, searchRegex, searchOptions, searchResults, searchStatus, searchError,
    setSearchQuery, setSearchRegex, setSearchOptions, setSearchStatus, setSearchResults, setSearchError,
    openTab } = useStore();

  async function run() {
    if (!sid || !searchQuery) return;
    setSearchStatus("loading"); setSearchError(null);
    try {
      const r = await searchContent(getWs(), sid, searchQuery, { regex: searchRegex, ...searchOptions });
      setSearchResults(r); setSearchStatus("done");
    } catch (err: any) {
      setSearchError(String(err?.message ?? err)); setSearchStatus("error"); setSearchResults(null);
    }
  }

  return (
    <div className="flex h-full flex-col gap-2 p-2 text-sm">
      <div className="flex items-center gap-1">
        <input className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1"
          placeholder="Buscar contenido…" value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }} />
        <button title="Regex" aria-pressed={searchRegex}
          className={`rounded px-1 ${searchRegex ? "bg-primary/30" : ""}`}
          onClick={() => setSearchRegex(!searchRegex)}>.*</button>
        <button title="Crear con IA" className="rounded px-1"
          onClick={() => sid && openTab({ id: `airegex:${sid}`, type: "airegex", label: "Regex IA" })}>✨</button>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <button aria-pressed={searchOptions.caseSensitive} className={`rounded px-1 ${searchOptions.caseSensitive ? "bg-primary/30" : ""}`}
          onClick={() => setSearchOptions({ caseSensitive: !searchOptions.caseSensitive })}>Aa</button>
        <button aria-pressed={searchOptions.wholeWord} className={`rounded px-1 ${searchOptions.wholeWord ? "bg-primary/30" : ""}`}
          onClick={() => setSearchOptions({ wholeWord: !searchOptions.wholeWord })}>ab|</button>
        <input className="w-24 rounded border border-border bg-background px-1" placeholder="incluir"
          value={searchOptions.include} onChange={(e) => setSearchOptions({ include: e.target.value })} />
        <input className="w-24 rounded border border-border bg-background px-1" placeholder="excluir"
          value={searchOptions.exclude} onChange={(e) => setSearchOptions({ exclude: e.target.value })} />
      </div>
      {searchStatus === "loading" && <div className="text-muted-foreground">buscando…</div>}
      {searchError && <div className="rounded border border-border bg-card p-1 text-xs text-muted-foreground">{searchError}</div>}
      {searchStatus === "done" && searchResults && (
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="mb-1 text-xs text-muted-foreground">
            {searchResults.total} resultado{searchResults.total === 1 ? "" : "s"} en {searchResults.files} archivo{searchResults.files === 1 ? "" : "s"}
            {searchResults.truncated && " (mostrando los primeros — refiná la búsqueda)"}
          </div>
          {searchResults.total === 0 && <div className="text-muted-foreground">Sin coincidencias</div>}
          {searchResults.matches.map((f) => (
            <div key={f.path} className="mb-1">
              <div className="text-xs font-medium text-foreground">{f.path}</div>
              {f.lines.map((l, k) => (
                <button key={k} className="block w-full truncate text-left font-mono text-xs hover:bg-card"
                  onClick={() => sid && openFile(getWs(), sid, f.path, l.line)}>
                  <span className="mr-2 text-muted-foreground">{l.line}</span>
                  <Highlighted text={l.text} ranges={l.ranges} />
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
