import { useEffect } from "react";
import "./modules/stubs";
import { applyTheme } from "./theme/tokens";
import { ActivityRail } from "./layout/ActivityRail";
import { ContextPanel } from "./layout/ContextPanel";
import { SessionsPanel } from "./modules/sessions/SessionsPanel";
import { NewSessionModal } from "./modules/sessions/NewSessionModal";
import { MainPanel } from "./layout/MainPanel";

export default function App() {
  useEffect(() => {
    applyTheme(document.documentElement);
  }, []);
  return (
    <div style={{ display: "flex", height: "100%" }}>
      <SessionsPanel />
      <ActivityRail />
      <ContextPanel />
      <MainPanel />
      <NewSessionModal />
    </div>
  );
}
