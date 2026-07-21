import type { Repo } from "./envelope";
// same-origin: la UI de cada instancia pega a su propio backend (mismo puerto), igual que wsUrl.
const BASE = typeof window !== "undefined" ? window.location.origin : "http://localhost:8787";
export async function getRepos(base: string = BASE): Promise<Repo[]> {
  const res = await fetch(`${base}/api/repos`);
  if (!res.ok) throw new Error(`repos ${res.status}`);
  return (await res.json()).repos as Repo[];
}
