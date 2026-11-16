import { OctagonAlert } from "lucide-react";
import { registerModule } from "../registry";
import { useFolders } from "../../state/folders";
import { LaterPanel } from "./LaterPanel";

// el ícono muestra cuántos bloqueantes quedan abiertos (de todos los desarrollos)
const useBadge = () => useFolders((s) => s.tree.later?.length ?? 0);
registerModule({ id: "later", title: "Bloqueantes", icon: OctagonAlert, Panel: LaterPanel, useBadge });
