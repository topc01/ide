export function wsUrl(env: { DEV: boolean }, loc: { protocol: string; host: string }): string {
  if (env.DEV) return "ws://localhost:8787/ws";                 // dev: Vite :5173 → backend :8787
  const proto = loc.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${loc.host}/ws`;                            // prod: mismo origen (puerto real)
}
