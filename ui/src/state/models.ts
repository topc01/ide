import { create } from "zustand";

export interface CuratedModel { repoId: string; label: string; params: string; quant: string; sizeGb: number; }
export interface InstalledModel { repoId: string; sizeOnDisk: number; }
export interface DownloadProgress { downloaded: number; total: number; error?: string; done?: boolean; }
export interface Catalog {
  curated: CuratedModel[]; installed: InstalledModel[];
  inUse: string | null; active: Record<string, { downloaded: number; total: number }>;
}

interface ModelsState {
  curated: CuratedModel[]; installed: InstalledModel[]; inUse: string | null;
  downloads: Record<string, DownloadProgress>;
  setCatalog: (c: Catalog) => void;
  applyEvent: (e: any) => void;
}

export const useModels = create<ModelsState>((set) => ({
  curated: [], installed: [], inUse: null, downloads: {},
  setCatalog: ({ curated, installed, inUse, active }) => set((s) => ({
    curated, installed, inUse,
    downloads: { ...Object.fromEntries(Object.entries(active).map(([r, p]) => [r, { ...p }])), ...s.downloads },
  })),
  applyEvent: (e) => set((s) => {
    const downloads = { ...s.downloads };
    const prev = downloads[e.repoId] ?? { downloaded: 0, total: 0 };
    if (e.kind === "progress") downloads[e.repoId] = { downloaded: e.downloaded, total: e.total };
    else if (e.kind === "done") downloads[e.repoId] = { ...prev, done: true };
    else if (e.kind === "error") downloads[e.repoId] = { ...prev, error: e.message };
    return { downloads };
  }),
}));
