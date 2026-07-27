import { useEffect, useRef } from "react";
import { useChat } from "../state/chat";
import { useStore } from "../state/store";
import { getWs } from "../transport/wsClient";
import { startChat, sendChat, interruptChat, subscribeChat } from "../transport/chatChannel";
import { MessageBubble } from "../chat/MessageBubble";
import { Composer } from "../chat/Composer";

export function extractRegex(text: string): string | null {
  const re = /```regex\s*\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null, last: string | null = null;
  while ((m = re.exec(text)) !== null) last = m[1].trim();
  return last;
}

export function RegexAiTab({ id }: { id: string }) {
  const { convos, applyEvent, setStarting, pushUser } = useChat();
  const { setSearchQuery, setSearchRegex, setActivePanel } = useStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setStarting(id, true);
    const unsub = subscribeChat(getWs(), id, (e) => applyEvent(id, e));
    startChat(getWs(), id)
      .catch((err) => applyEvent(id, { kind: "error", code: "chat_error", message: String(err?.message ?? err) }))
      .finally(() => setStarting(id, false));
    return unsub;
  }, [id, applyEvent, setStarting]);

  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); });

  const c = convos[id];
  const lastAgent = [...(c?.messages ?? [])].reverse().find((m) => m.role === "agent");
  const regex = lastAgent ? extractRegex(lastAgent.text ?? "") : null;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-2 text-xs text-muted-foreground">
        Asistente de regex — describí qué querés buscar.
      </div>
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
        {c?.messages.map((m, i) => <MessageBubble key={i} msg={m} />)}
      </div>
      {regex && (
        <div className="flex items-center gap-2 border-t border-border p-2">
          <code className="min-w-0 flex-1 truncate rounded bg-card px-2 py-1 text-xs">{regex}</code>
          <button className="rounded bg-primary/30 px-2 py-1 text-xs"
            onClick={() => { setSearchRegex(true); setSearchQuery(regex); setActivePanel("search"); }}>
            Insertar regex
          </button>
        </div>
      )}
      <Composer streaming={!!c?.streaming}
        onSend={(t) => { pushUser(id, t); sendChat(getWs(), id, t).catch((err) =>
          applyEvent(id, { kind: "error", code: "chat_error", message: String(err?.message ?? err) })); }}
        onStop={() => interruptChat(getWs(), id)} />
    </div>
  );
}
