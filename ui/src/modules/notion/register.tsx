import { BookOpen } from "lucide-react";
import { registerModule } from "../registry";
import { NotionPanel } from "./NotionPanel";
registerModule({ id: "notion", title: "Notion", icon: BookOpen, Panel: NotionPanel });
