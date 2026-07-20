import { create } from "zustand";
import type { TaskRef } from "../transport/tasksChannel";
import { listTasks, createTask } from "../transport/tasksChannel";
import { getWs } from "../transport/wsClient";

interface TasksState {
  tasks: TaskRef[]; loading: boolean; error: string | null;
  load: () => Promise<void>;
  create: (name: string) => Promise<TaskRef | undefined>;
}
const msg = (e: unknown) => (e as { message?: string })?.message ?? "desconectado";

export const useTasks = create<TasksState>((set) => ({
  tasks: [], loading: false, error: null,
  load: async () => {
    set({ loading: true });
    try { set({ tasks: await listTasks(getWs()), loading: false, error: null }); }
    catch (e) { set({ loading: false, error: msg(e) }); }
  },
  create: async (name) => {
    try {
      const ref = await createTask(getWs(), name);
      set({ tasks: await listTasks(getWs()), error: null });
      return ref;
    } catch (e) { set({ error: msg(e) }); return undefined; }
  },
}));
