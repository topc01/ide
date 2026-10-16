import { Layers2 } from "lucide-react";
import { registerModule } from "../registry";
import { GithubPanel } from "./GithubPanel";

registerModule({ id: "stack", title: "Stack", icon: Layers2, Panel: GithubPanel });
