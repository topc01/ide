import { useState } from "react";
import { Send, Square } from "lucide-react";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";

export function Composer({ onSend, onStop, streaming }:
  { onSend: (t: string, route?: "local" | "claude") => void; onStop: () => void; streaming: boolean }) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"auto" | "local" | "claude">("auto");
  const submit = () => {
    const t = text.trim(); if (!t) return;
    onSend(t, mode === "auto" ? undefined : mode);
    setText("");
  };
  return (
    <div className="flex items-center gap-2 border-t border-border p-2">
      <select value={mode} onChange={(e) => setMode(e.target.value as "auto" | "local" | "claude")}
        aria-label="ruteo del mensaje" title="a quién va el mensaje"
        className="rounded border border-border bg-transparent px-1.5 py-1.5 text-[11px] text-muted-foreground">
        <option value="auto">Auto</option>
        <option value="local">Local</option>
        <option value="claude">Claude</option>
      </select>
      <Input value={text} onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
        placeholder="Escribe un mensaje…" className="flex-1" />
      {streaming ? (
        <Button variant="secondary" size="icon" aria-label="detener" title="detener" onClick={onStop}>
          <Square size={16} />
        </Button>
      ) : (
        <Button size="icon" aria-label="enviar" title="enviar" onClick={submit}>
          <Send size={16} />
        </Button>
      )}
    </div>
  );
}
