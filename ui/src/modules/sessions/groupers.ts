import type { FolderSession } from "../../transport/folderSessions";

export interface Section { id: string; label: string; defaultOpen: boolean; }
export interface Grouper {
  id: string; label: string; sections: Section[]; sectionOf: (s: FolderSession) => string;
}

const groupers: Grouper[] = [];
export function registerGrouper(g: Grouper) { if (!groupers.some((x) => x.id === g.id)) groupers.push(g); }
export function getGroupers(): Grouper[] { return groupers; }
export function getGrouper(id: string): Grouper { return groupers.find((g) => g.id === id) ?? groupers[0]; }

export function groupSessions(sessions: FolderSession[], g: Grouper) {
  return g.sections
    .map((section) => ({ section, items: sessions.filter((s) => g.sectionOf(s) === section.id) }))
    .filter((x) => x.items.length > 0);
}

registerGrouper({
  id: "none", label: "Sin agrupar",
  sections: [{ id: "all", label: "Sesiones", defaultOpen: true }], sectionOf: () => "all",
});

const ATTENTION = ["blocked", "questions", "ready"];
registerGrouper({
  id: "status", label: "Por estado",
  sections: [
    { id: "active", label: "En curso", defaultOpen: true },
    { id: "attention", label: "Necesitan tu atención", defaultOpen: true },
    { id: "queued", label: "En cola", defaultOpen: true },
    { id: "done", label: "Hechos", defaultOpen: false },
  ],
  sectionOf: (s) => s.process === "queued" ? "queued"
    : s.status === "done" ? "done"
    : ATTENTION.includes(s.status ?? "") ? "attention" : "active",
});
