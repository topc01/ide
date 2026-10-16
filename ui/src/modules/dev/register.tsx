import { LayoutList } from "lucide-react";
import { registerModule } from "../registry";
import { DevPanel } from "./DevPanel";

registerModule({ id: "dev", title: "Desarrollo", icon: LayoutList, Panel: DevPanel });
