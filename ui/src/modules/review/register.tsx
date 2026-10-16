import { MessagesSquare } from "lucide-react";
import { registerModule } from "../registry";
import { ReviewPanel } from "./ReviewPanel";

registerModule({ id: "review", title: "Revisión", icon: MessagesSquare, Panel: ReviewPanel });
