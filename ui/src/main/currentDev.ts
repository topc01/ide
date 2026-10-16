// ui/src/main/currentDev.ts
import { useFolders } from "../state/folders";
import type { FolderSession, GhPr } from "../transport/folderSessions";
import { allPrs, useGithubReviews } from "../modules/sessions/ReviewsSection";
import { deriveMine } from "../modules/sessions/desarrollos";

export interface Dev { key: string; session?: FolderSession; prs: GhPr[] }

/** El desarrollo actual: una sesión (con sus PRs), un stack sin sesión o una PR suelta. */
export function useCurrentDev(): Dev | null {
  const { tree, activeId, activePrUrl } = useFolders();
  const { gh } = useGithubReviews();
  const tickets = tree.sessions.filter((s) => s.kind !== "review");
  if (activePrUrl) {
    if (!gh) return null;                     // hasta tener datos no se sabe a qué desarrollo pertenece
    const owner = deriveMine(tickets, gh).find((d) => d.session && d.prs.some((p) => p.url === activePrUrl));
    if (owner) return { key: `s:${owner.session!.id}`, session: owner.session, prs: owner.prs };
    const pr = allPrs(gh).find((p) => p.url === activePrUrl);
    if (pr?.stack) return { key: `st:${pr.stack.id}`, prs: gh.stacks?.[pr.stack.id] ?? [pr] };
    return { key: `p:${activePrUrl}`, prs: pr ? [pr] : [] };
  }
  const session = tree.sessions.find((s) => s.id === activeId);
  if (!session) return null;
  const prs = gh ? (session.kind === "review"
    ? allPrs(gh).filter((p) => p.sessionId === session.id)
    : deriveMine(tickets, gh).find((d) => d.session?.id === session.id)?.prs ?? []) : [];
  return { key: `s:${session.id}`, session, prs };
}
