import { CircleHelp } from "lucide-react";
import { registerModule } from "../registry";
import { useFolders } from "../../state/folders";
import { LaterPanel } from "./LaterPanel";

// el ícono muestra cuántas decisiones quedan abiertas (de todos los desarrollos)
const useBadge = () => useFolders((s) => s.tree.later?.length ?? 0);
registerModule({ id: "later", title: "Decisiones", icon: CircleHelp, Panel: LaterPanel, useBadge });
