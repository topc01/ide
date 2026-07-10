/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--background)", foreground: "var(--foreground)",
        card: { DEFAULT: "var(--card)", foreground: "var(--card-foreground)" },
        popover: { DEFAULT: "var(--popover)", foreground: "var(--popover-foreground)" },
        primary: { DEFAULT: "var(--primary)", foreground: "var(--primary-foreground)" },
        muted: { DEFAULT: "var(--muted)", foreground: "var(--muted-foreground)" },
        accent: { DEFAULT: "var(--accent)", foreground: "var(--accent-foreground)" },
        border: "var(--border)", input: "var(--input)", ring: "var(--ring)",
        "title-bg": "var(--title-bg)", "terminal-bg": "var(--terminal-bg)",
        "status-running": "var(--status-running)", "status-idle": "var(--status-idle)",
        "status-done": "var(--status-done)", "role-pill": "var(--role-pill-bg)",
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      fontFamily: { mono: ['"JetBrains Mono"', "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
};
