export type EnvType = "req" | "res" | "event" | "error";
export interface Envelope { type: EnvType; id: string | null; channel: string; payload: any; }
export interface Repo { id: string; name: string; branch: string; }
