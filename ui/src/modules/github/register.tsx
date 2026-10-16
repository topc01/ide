import { Github } from "lucide-react";
import { registerModule } from "../registry";
import { GithubPanel } from "./GithubPanel";

registerModule({ id: "github", title: "GitHub", icon: Github, Panel: GithubPanel });
