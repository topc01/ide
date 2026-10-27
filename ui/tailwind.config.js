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
        // estos tonos cambian con el tema (index.css): en claro se oscurecen para leerse sobre papel
        amber: { 300: "rgb(var(--amber-300) / <alpha-value>)" },
        emerald: { 300: "rgb(var(--emerald-300) / <alpha-value>)", 400: "rgb(var(--emerald-400) / <alpha-value>)" },
        orange: { 300: "rgb(var(--orange-300) / <alpha-value>)" },
        purple: { 300: "rgb(var(--purple-300) / <alpha-value>)", 400: "rgb(var(--purple-400) / <alpha-value>)" },
        red: { 400: "rgb(var(--red-400) / <alpha-value>)" },
        sky: { 300: "rgb(var(--sky-300) / <alpha-value>)", 400: "rgb(var(--sky-400) / <alpha-value>)" },
        yellow: { 300: "rgb(var(--yellow-300) / <alpha-value>)" },
        zinc: { 300: "rgb(var(--zinc-300) / <alpha-value>)" },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      fontFamily: { mono: ['"JetBrains Mono"', "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
};
