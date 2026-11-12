import { BookOpen } from "lucide-react";
import { registerModule } from "../registry";
import { TicketsPanel } from "./TicketsPanel";
// los tickets de Notion del desarrollo elegido: el de la sesión, sus subtickets (con el interruptor de la card) y los pendientes
registerModule({ id: "notion", title: "Notion", icon: BookOpen, Panel: TicketsPanel });
