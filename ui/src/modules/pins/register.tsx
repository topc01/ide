import { Pin } from "lucide-react";
import { registerModule } from "../registry";
import { PinsPanel } from "./PinsPanel";

registerModule({ id: "pins", title: "Pines", icon: Pin, Panel: PinsPanel });
