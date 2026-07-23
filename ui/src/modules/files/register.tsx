import { FolderTree } from "lucide-react";
import { registerModule } from "../registry";
import { FilesPanel } from "./FilesPanel";

registerModule({ id: "files", title: "Files", icon: FolderTree, Panel: FilesPanel });
