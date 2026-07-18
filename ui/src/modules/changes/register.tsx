import { FileDiff } from "lucide-react";
import { registerModule } from "../registry";
import { ChangesPanel } from "./ChangesPanel";

registerModule({ id: "changes", title: "Changed files", icon: FileDiff, Panel: ChangesPanel });
