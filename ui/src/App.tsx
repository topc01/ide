import { useEffect } from "react";
import "./modules/stubs";
import { applyTheme } from "./theme/tokens";
import { getRepos } from "./transport/rest";
import { useStore } from "./state/store";
import { ActivityRail } from "./layout/ActivityRail";
import { ContextPanel } from "./layout/ContextPanel";
import { Sidebar } from "./layout/Sidebar";
import { MainPanel } from "./layout/MainPanel";

export default function App() {
  const setRepos = useStore((s) => s.setRepos);
  useEffect(() => {
    applyTheme(document.documentElement);
    getRepos().then(setRepos).catch(() => setRepos([]));
  }, [setRepos]);
  return (
    <div style={{ display: "flex", height: "100%" }}>
      <Sidebar />
      <ActivityRail />
      <ContextPanel />
      <MainPanel />
    </div>
  );
}
