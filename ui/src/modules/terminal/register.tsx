import { SquareTerminal } from "lucide-react";
import { registerModule } from "../registry";
import { TerminalPanel } from "./TerminalPanel";

registerModule({ id: "terminal", title: "Terminal", icon: SquareTerminal, Panel: TerminalPanel });
