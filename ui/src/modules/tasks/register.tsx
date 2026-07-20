import { ListChecks } from "lucide-react";
import { registerModule } from "../registry";
import { TasksPanel } from "./TasksPanel";
registerModule({ id: "tasks", title: "Tasks", icon: ListChecks, Panel: TasksPanel });
