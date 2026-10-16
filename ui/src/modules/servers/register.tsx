import { Server } from "lucide-react";
import { registerModule } from "../registry";
import { ServersPanel } from "./ServersPanel";

registerModule({ id: "servers", title: "Servidores", icon: Server, Panel: ServersPanel });
