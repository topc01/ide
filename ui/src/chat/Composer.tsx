import { useState } from "react";
import { Send, Square } from "lucide-react";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";

export function Composer({ onSend, onStop, streaming }:
  { onSend: (t: string) => void; onStop: () => void; streaming: boolean }) {
  const [text, setText] = useState("");
  const submit = () => { const t = text.trim(); if (!t) return; onSend(t); setText(""); };
  return (
    <div className="flex items-center gap-2 border-t border-border p-2">
      <Input value={text} onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
        placeholder="Escribí un mensaje…" className="flex-1" />
      {streaming ? (
        <Button variant="secondary" size="icon" aria-label="detener" onClick={onStop}>
          <Square size={16} />
        </Button>
      ) : (
        <Button size="icon" aria-label="enviar" onClick={submit}>
          <Send size={16} />
        </Button>
      )}
    </div>
  );
}
