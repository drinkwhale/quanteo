/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // The Silent Exchange 팔레트 별칭 (기존 컴포넌트 클래스 호환 유지)
        surface: "var(--background)",
        panel: "var(--card)",
        border: "var(--border)",
        accent: "var(--accent)",
        "accent-hover": "var(--color-signal-blue-deep)",
        positive: "var(--color-live-green)",
        negative: "var(--destructive)",
        warning: "var(--color-caution-amber)",
        muted: "var(--muted-foreground)",
        ink: "var(--foreground)",

        // shadcn/ui 시맨틱 슬롯 (컴포넌트 추가 시 자동으로 다크 팔레트 적용)
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        input: "var(--input)",
        ring: "var(--ring)",
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};
