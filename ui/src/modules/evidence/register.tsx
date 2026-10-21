import { Camera } from "lucide-react";
import { registerModule } from "../registry";
import { EvidencePanel } from "./EvidencePanel";

registerModule({ id: "evidence", title: "Evidencias", icon: Camera, Panel: EvidencePanel });
