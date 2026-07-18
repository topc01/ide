import "./modules/stubs";
import "./modules/terminal/register";
import "./modules/changes/register";
import "./modules/graphite/register";
import "./modules/notion/register";
import { ActivityRail } from "./layout/ActivityRail";
import { ContextPanel } from "./layout/ContextPanel";
import { SessionsPanel } from "./modules/sessions/SessionsPanel";
import { NewSessionModal } from "./modules/sessions/NewSessionModal";
import { SettingsModal } from "./modules/settings/SettingsModal";
import { MainPanel } from "./layout/MainPanel";

export default function App() {
  return (
    <div className="flex h-full">
      <SessionsPanel />
      <ActivityRail />
      <ContextPanel />
      <MainPanel />
      <NewSessionModal />
      <SettingsModal />
    </div>
  );
}
