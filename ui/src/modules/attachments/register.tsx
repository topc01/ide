import { Paperclip } from "lucide-react";
import { registerModule } from "../registry";
import { AttachmentsPanel } from "./AttachmentsPanel";

registerModule({ id: "attachments", title: "Adjuntos", icon: Paperclip, Panel: AttachmentsPanel });
