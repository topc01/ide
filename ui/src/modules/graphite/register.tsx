import { Layers } from "lucide-react";
import { registerModule } from "../registry";
import { GraphitePanel } from "./GraphitePanel";

registerModule({ id: "graphite", title: "Graphite", icon: Layers, Panel: GraphitePanel });
