import { MessageSquareText } from "lucide-react";
import { registerModule } from "../registry";
import { PromptsPanel } from "./PromptsPanel";

registerModule({ id: "prompts", title: "Prompts", icon: MessageSquareText, Panel: PromptsPanel });
