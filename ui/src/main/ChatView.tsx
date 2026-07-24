import { useEffect, useRef } from "react";
import { useChat } from "../state/chat";
import { useSessions } from "../state/sessions";
import { getWs } from "../transport/wsClient";
import { startChat, sendChat, interruptChat, permissionDecision, subscribeChat } from "../transport/chatChannel";
import { MessageBubble } from "../chat/MessageBubble";
import { Composer } from "../chat/Composer";
import { PermissionPrompt } from "../chat/PermissionPrompt";

export function ChatView() {
  const activeSessionId = useSessions((s) => s.activeSessionId);
  const { convos, applyEvent, setStarting, pushUser, clearPermission } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const sid = activeSessionId;

  useEffect(() => {
    if (!sid) return;
    setStarting(sid, true);
    const unsub = subscribeChat(getWs(), sid, (e) => applyEvent(sid, e));
    startChat(getWs(), sid)
      .catch((err) => applyEvent(sid, { kind: "error", code: "chat_error", message: String(err?.message ?? err) }))
      .finally(() => setStarting(sid, false));
    return unsub;
  }, [sid, applyEvent, setStarting]);

  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); });

  if (!sid) {
    return <div className="p-4 text-sm text-muted-foreground">Seleccioná una sesión para chatear.</div>;
  }
  const c = convos[sid];
  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
        {c?.starting && (!c || c.messages.length === 0) && (
          <div className="text-sm text-muted-foreground">Arrancando Claude Code…</div>)}
        {c?.messages.map((m, i) => <MessageBubble key={i} msg={m} />)}
        {c?.error && (
          <div className="rounded-md border border-border bg-card p-2 text-xs text-muted-foreground">
            {c.error.message}</div>)}
      </div>
      {c?.permission && (
        <PermissionPrompt tool={c.permission.tool} detail={c.permission.detail}
          onDecide={(allow) => {
            permissionDecision(getWs(), sid, c.permission!.id, allow);
            clearPermission(sid);
          }} />)}
      <Composer streaming={!!c?.streaming}
        onSend={(t, route) => {
          pushUser(sid, t);
          sendChat(getWs(), sid, t, route).catch((err) =>
            applyEvent(sid, { kind: "error", code: "chat_error", message: String(err?.message ?? err) }));
        }}
        onStop={() => interruptChat(getWs(), sid)} />
    </div>
  );
}
