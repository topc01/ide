import { create } from "zustand";
import type { Item } from "../transport/settingsChannel";
interface SettingsState {
  items: Item[]; open: boolean; selectedKey: string;
  setData: (items: Item[]) => void;
  openSettings: (key: string) => void;
  closeSettings: () => void;
}
export const useSettings = create<SettingsState>((set) => ({
  items: [], open: false, selectedKey: "overview",
  setData: (items) => set({ items }),
  openSettings: (selectedKey) => set({ open: true, selectedKey }),
  closeSettings: () => set({ open: false }),
}));
