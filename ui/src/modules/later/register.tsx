import { OctagonAlert } from "lucide-react";
import { registerModule } from "../registry";
import { useFolders } from "../../state/folders";
import { LaterPanel } from "./LaterPanel";
import { activeBlockers } from "./focus";

// el ícono muestra cuántos bloqueantes están en curso (sin los de desarrollos pausados o archivados)
const useBadge = () => useFolders(activeBlockers);
registerModule({ id: "later", title: "Bloqueantes", icon: OctagonAlert, Panel: LaterPanel, useBadge });
