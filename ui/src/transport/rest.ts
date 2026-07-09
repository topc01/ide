import type { Repo } from "./envelope";
const BASE = "http://localhost:8787";
export async function getRepos(base: string = BASE): Promise<Repo[]> {
  const res = await fetch(`${base}/api/repos`);
  if (!res.ok) throw new Error(`repos ${res.status}`);
  return (await res.json()).repos as Repo[];
}
