/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Tech Green Dark Mode 팔레트 별칭 — rgb(var(--x) / <alpha-value>) 패턴 필수.
        // CSS 변수가 hex 문자열이면 Tailwind가 opacity modifier(/40, /10 등) 유틸을
        // 아예 생성하지 않는다(콘솔 에러 없이 클래스 자체가 빌드에서 빠짐 — 조용히 실패).
        // 변수는 R G B 트리플릿(index.css)이어야 한다.
        surface: "rgb(var(--background) / <alpha-value>)",
        panel: "rgb(var(--card) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-hover": "rgb(var(--color-emerald-deep) / <alpha-value>)",
        positive: "rgb(var(--color-live-green) / <alpha-value>)",
        negative: "rgb(var(--destructive) / <alpha-value>)",
        warning: "rgb(var(--color-caution-amber) / <alpha-value>)",
        muted: "rgb(var(--muted-foreground) / <alpha-value>)",
        ink: "rgb(var(--foreground) / <alpha-value>)",

        // shadcn/ui 시맨틱 슬롯 (컴포넌트 추가 시 자동으로 다크 팔레트 적용)
        background: "rgb(var(--background) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)",
        card: {
          DEFAULT: "rgb(var(--card) / <alpha-value>)",
          foreground: "rgb(var(--card-foreground) / <alpha-value>)",
        },
        popover: {
          DEFAULT: "rgb(var(--popover) / <alpha-value>)",
          foreground: "rgb(var(--popover-foreground) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          foreground: "rgb(var(--primary-foreground) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "rgb(var(--secondary) / <alpha-value>)",
          foreground: "rgb(var(--secondary-foreground) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "rgb(var(--destructive) / <alpha-value>)",
          foreground: "rgb(var(--destructive-foreground) / <alpha-value>)",
        },
        input: "rgb(var(--input) / <alpha-value>)",
        ring: "rgb(var(--ring) / <alpha-value>)",
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
      },
      fontFamily: {
        sans: [
          "Pretendard Variable",
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "sans-serif",
        ],
        // 시스템 라벨·타임스탬프·종목코드 전용 — 웹폰트 추가 로드 없이 OS 내장 모노 사용
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "JetBrains Mono",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
