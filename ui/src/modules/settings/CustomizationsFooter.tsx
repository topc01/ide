import { useEffect } from "react";
import { useSettings } from "../../state/settings";
import { fetchCustomizations } from "../../transport/settingsChannel";
import { getWs } from "../../transport/wsClient";

export function CustomizationsFooter() {
  const { items, setData, openSettings } = useSettings();
  useEffect(() => {
    fetchCustomizations(getWs()).then(setData).catch(() => setData([]));
  }, [setData]);
  return (
    <div className="mt-auto border-t border-border py-1">
      {items.map((i) => (
        <button title="Ver esta customización" key={i.key} onClick={() => openSettings(i.key)}
          className="flex w-full items-center justify-between px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground">
          <span>{i.title}</span>
          {i.count > 0 && <span className="text-[10px]">{i.count}</span>}
        </button>
      ))}
    </div>
  );
}
