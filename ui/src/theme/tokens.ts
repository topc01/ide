export const tokens = {
  appBg: "#161513", panelBg: "#1c1a17", titleBg: "#131210", terminalBg: "#0f0e0c",
  agentBubble: "#211e1a", border: "#332f28", borderSoft: "#2a2721",
  textPrimary: "#f0ece4", textSecondary: "#cfc9bd", textMuted: "#75705f",
  accent: "#e0863f", accentHover: "#eb954f", onAccent: "#161513",
  selectedBg: "#2e2820", statusRunning: "#7fb069", statusIdle: "#7d7568", statusDone: "#6b8fbf",
} as const;

const VARS: Record<string, keyof typeof tokens> = {
  "--app-bg": "appBg", "--panel-bg": "panelBg", "--title-bg": "titleBg",
  "--terminal-bg": "terminalBg", "--agent-bubble": "agentBubble", "--border": "border",
  "--border-soft": "borderSoft", "--text-primary": "textPrimary",
  "--text-secondary": "textSecondary", "--text-muted": "textMuted",
  "--accent": "accent", "--accent-hover": "accentHover", "--on-accent": "onAccent",
  "--selected-bg": "selectedBg",
  "--status-running": "statusRunning", "--status-idle": "statusIdle", "--status-done": "statusDone",
};

export function applyTheme(root: HTMLElement): void {
  for (const [cssVar, key] of Object.entries(VARS)) root.style.setProperty(cssVar, tokens[key]);
}
