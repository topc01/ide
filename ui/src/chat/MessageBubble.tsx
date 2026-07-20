import { Clock, Pencil } from "lucide-react";
import { cn } from "../lib/utils";
import type { Msg } from "../state/chat";

export function MessageBubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex flex-col gap-1", isUser ? "items-end" : "items-start")}>
      {msg.relay && (
        <span className="text-[11px] font-medium" style={{ color: "#e0863f" }}>
          {msg.relay.direction === "out" ? "→" : "←"} {msg.relay.peer}
        </span>
      )}
      <div data-bubble className={cn("max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
        isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground")}>
        {msg.text}
      </div>
      {msg.chips.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {msg.chips.map((chip, i) =>
            chip.kind === "tool" ? (
              <div key={i} className="flex items-center gap-1.5 text-[11px]">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#a5703c" }} />
                <span style={{ color: "#bd925f" }}>{chip.name}</span>
                <span className="font-mono text-muted-foreground">{chip.detail}</span>
              </div>
            ) : (
              <div key={i} className="flex items-center gap-1.5 text-[11px]">
                <Pencil size={11} style={{ color: "#a5703c" }} />
                <span style={{ color: "#bd925f" }}>Edit</span>
                <span className="font-mono text-muted-foreground">{chip.path}</span>
                <span style={{ color: "#9fcf87" }}>+{chip.added}</span>
                <span style={{ color: "#d89a89" }}>-{chip.removed}</span>
              </div>
            ))}
        </div>
      )}
      {msg.tokens != null && (
        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <Clock size={11} /> {msg.tokens.toLocaleString()} tokens
        </div>
      )}
    </div>
  );
}
