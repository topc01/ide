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
import { ActivityRail } from "./layout/ActivityRail";
import { ContextPanel } from "./layout/ContextPanel";
import { FolderSessionsPanel } from "./modules/sessions/FolderSessionsPanel";
import { NewFolderSessionModal } from "./modules/sessions/NewFolderSessionModal";
import { SettingsModal } from "./modules/settings/SettingsModal";
import { MainPanel } from "./layout/MainPanel";

export default function App() {
  const setUiModules = useFolders((s) => s.setUiModules);
  const setConnected = useFolders((s) => s.setConnected);
  useEffect(() => {
    fetchUiConfig(getWs()).then((c) => setUiModules(c.modules)).catch(() => setConnected(false));
  }, [setUiModules, setConnected]);
  return (
    <div className="flex h-full">
      <FolderSessionsPanel />
      <ActivityRail />
      <ContextPanel />
      <MainPanel />
      <SettingsModal />
      <NewFolderSessionModal />
    </div>
  );
}
