import { Settings2 } from "lucide-react";
import { registerModule } from "../registry";
import { ConfigPanel } from "./ConfigPanel";

registerModule({ id: "config", title: "Configuración", icon: Settings2, Panel: ConfigPanel });
