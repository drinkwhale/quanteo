/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0f1117",
        panel: "#1a1d27",
        border: "#2a2d3a",
        accent: "#3b82f6",
        "accent-hover": "#2563eb",
        positive: "#22c55e",
        negative: "#ef4444",
        warning: "#f59e0b",
        muted: "#6b7280",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};
