import { Clock } from "lucide-react";
import { registerModule } from "../registry";
import { LaterPanel } from "./LaterPanel";

registerModule({ id: "later", title: "Para después", icon: Clock, Panel: LaterPanel });
