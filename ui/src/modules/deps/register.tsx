import { Link2 } from "lucide-react";
import { registerModule } from "../registry";
import { DepsPanel } from "./DepsPanel";

registerModule({ id: "deps", title: "Dependencias", icon: Link2, Panel: DepsPanel });
