import { Presentation } from "lucide-react";
import { registerModule } from "../registry";
import { ArtifactsPanel } from "./ArtifactsPanel";
// los artefactos (páginas de claude.ai) que publicó la sesión del desarrollo elegido, con el interruptor de la card
registerModule({ id: "artifacts", title: "Artefactos", icon: Presentation, Panel: ArtifactsPanel });
