import { create } from "zustand";

export type Chip =
  | { kind: "tool"; name: string; detail: string }
  | { kind: "edit"; path: string; added: number; removed: number };
export interface Msg { role: "user" | "agent"; text: string; chips: Chip[]; tokens?: number }
interface Convo {
  messages: Msg[]; streaming: boolean;
  permission: { id: string; tool: string; detail: string } | null;
  error: { code: string; message: string } | null; starting: boolean;
}
interface ChatState {
  convos: Record<string, Convo>;
  applyEvent: (sid: string, e: any) => void;
  setStarting: (sid: string, v: boolean) => void;
  pushUser: (sid: string, text: string) => void;
  clearPermission: (sid: string) => void;
}

const empty = (): Convo => ({ messages: [], streaming: false, permission: null, error: null, starting: false });

function lastAgent(c: Convo): Msg {
  const last = c.messages[c.messages.length - 1];
  if (last && last.role === "agent") return last;
  const m: Msg = { role: "agent", text: "", chips: [] };
  c.messages.push(m);
  return m;
}

export const useChat = create<ChatState>((set) => ({
  convos: {},
  setStarting: (sid, v) => set((s) => {
    const c = { ...(s.convos[sid] ?? empty()), starting: v };
    return { convos: { ...s.convos, [sid]: c } };
  }),
  pushUser: (sid, text) => set((s) => {
    const c = { ...(s.convos[sid] ?? empty()) };
    c.messages = [...c.messages, { role: "user", text, chips: [] }];
    c.streaming = true;
    return { convos: { ...s.convos, [sid]: c } };
  }),
  clearPermission: (sid) => set((s) => {
    const c = { ...(s.convos[sid] ?? empty()), permission: null };
    return { convos: { ...s.convos, [sid]: c } };
  }),
  applyEvent: (sid, e) => set((s) => {
    const c: Convo = { ...(s.convos[sid] ?? empty()) };
    c.messages = c.messages.map((m) => ({ ...m, chips: [...m.chips] }));
    if (e.kind === "text_delta") { lastAgent(c).text += e.text; }
    else if (e.kind === "tool_use") { lastAgent(c).chips.push({ kind: "tool", name: e.name, detail: e.detail }); }
    else if (e.kind === "edit") { lastAgent(c).chips.push({ kind: "edit", path: e.path, added: e.added, removed: e.removed }); }
    else if (e.kind === "usage") { lastAgent(c).tokens = e.totalTokens; }
    else if (e.kind === "done") { c.streaming = false; }
    else if (e.kind === "permission_request") { c.permission = { id: e.id, tool: e.tool, detail: e.detail }; }
    else if (e.kind === "error") { c.error = { code: e.code, message: e.message }; c.streaming = false; }
    return { convos: { ...s.convos, [sid]: c } };
  }),
}));
