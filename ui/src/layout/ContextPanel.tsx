import { useStore } from "../state/store";
import { getModules } from "../modules/registry";

export function ContextPanel() {
  const { activePanel } = useStore();
  const mod = getModules().find((m) => m.id === activePanel);
  const Panel = mod?.Panel;
  return (
    <aside style={{ width: 264, background: "var(--panel-bg)", borderRight: "1px solid var(--border)", overflow: "auto" }}>
      {Panel ? <Panel /> : null}
    </aside>
  );
}
