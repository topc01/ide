import { Search } from "lucide-react";
import { registerModule } from "../registry";
import { SearchPanel } from "./SearchPanel";
registerModule({ id: "search", title: "Search", icon: Search, Panel: SearchPanel });
