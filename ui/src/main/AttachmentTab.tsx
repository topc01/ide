// ui/src/main/AttachmentTab.tsx
import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { attachmentUrl } from "../transport/folderSessions";

const IMG = /\.(png|jpe?g|gif|webp|bmp|avif)$/i;
const TEXT = /\.(txt|md|csv|tsv|json|log|ya?ml|toml|xml|html?|css|js|ts|tsx|jsx|py|sql|sh|env|ini)$/i;

/** Un adjunto de la sesión: imagen o PDF en línea, texto legible, lo demás para descargar. */
export function AttachmentTab({ sid, name }: { sid: string; name: string }) {
  const url = attachmentUrl(sid, name);
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    setText(null);
    if (TEXT.test(name)) fetch(url).then((r) => r.text()).then((t) => setText(t.slice(0, 2_000_000))).catch(() => setText(null));
  }, [url, name]);
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3 py-1 text-xs">
        <span className="min-w-0 truncate font-mono">{name}</span>
        <span className="flex-1" />
        <a href={attachmentUrl(sid, name, true)} title="Descargar" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
          <Download size={12} /> Descargar</a>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {IMG.test(name) ? <img src={url} alt={name} className="mx-auto max-h-full max-w-full object-contain p-4" />
          : /\.pdf$/i.test(name) ? <iframe src={url} title={name} className="h-full w-full border-0" />
          : TEXT.test(name) ? <pre className="whitespace-pre-wrap break-words p-4 font-mono text-xs">{text ?? "cargando…"}</pre>
          : <p className="p-6 text-sm text-muted-foreground">Sin vista previa para este tipo de archivo: descárgalo.</p>}
      </div>
    </div>
  );
}
