import { Search } from "lucide-react";
import { registerModule, getModules } from "./registry";

const Stub = (label: string): React.FC => () => (
  <div style={{ padding: 12, color: "var(--text-muted)" }}>{label} — próximamente</div>
);

registerModule({ id: "search", title: "Search", icon: Search, Panel: Stub("Search") });

export { getModules };
