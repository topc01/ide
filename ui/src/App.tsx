import { useEffect } from "react";
import { useFolders } from "./state/folders";
import { fetchUiConfig } from "./transport/folderSessions";
import { getWs } from "./transport/wsClient";
import "./modules/search/register";
import "./modules/terminal/register";
import "./modules/changes/register";
import "./modules/graphite/register";
import "./modules/notion/register";
import "./modules/tasks/register";
import "./modules/files/register";
import "./modules/dev/register";
import "./modules/prompts/register";
import "./modules/github/register";
import "./modules/review/register";
import "./modules/deps/register";
import "./modules/servers/register";
import "./modules/db/register";
import "./modules/pins/register";
import "./modules/later/register";
import "./modules/evidence/register";
import "./modules/attachments/register";
import "./modules/explorer/register";
import "./modules/config/register";
import { ActionMenu } from "./layout/ActionMenu";
import { InnerSidebar } from "./layout/InnerSidebar";
import { MainSidebar } from "./modules/sessions/MainSidebar";
import { NewFolderSessionModal } from "./modules/sessions/NewFolderSessionModal";
import { SettingsModal } from "./modules/settings/SettingsModal";
import { MainPanel } from "./layout/MainPanel";
import { StatusBar } from "./layout/StatusBar";
import { DevSelector } from "./layout/DevSelector";
import { HoverTips } from "./layout/HoverTips";
import { useDevShortcuts } from "./layout/devShortcuts";
import { DevSwitcher } from "./layout/DevSwitcher";

export default function App() {
  useDevShortcuts();
  const setUiModules = useFolders((s) => s.setUiModules);
  const setConnected = useFolders((s) => s.setConnected);
  useEffect(() => {
    fetchUiConfig(getWs()).then((c) => setUiModules(c.modules)).catch(() => setConnected(false));
  }, [setUiModules, setConnected]);
  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        <MainSidebar />
        <div className="flex min-h-0 flex-col">
          <DevSelector />
          <div className="flex min-h-0 flex-1">
            <ActionMenu />
            <InnerSidebar />
          </div>
        </div>
        <MainPanel />
      </div>
      <StatusBar />
      <HoverTips />
      <DevSwitcher />
      <SettingsModal />
      <NewFolderSessionModal />
    </div>
  );
}
