import { FolderTree } from "lucide-react";
import { registerModule } from "../registry";
import { ExplorerPanel } from "./ExplorerPanel";

registerModule({ id: "explorer", title: "Archivos", icon: FolderTree, Panel: ExplorerPanel });
