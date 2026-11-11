/** rgb(var(--x) / <alpha-value>) 패턴 필수 — 변수가 hex면 opacity modifier(/40 등)
 * 유틸이 에러 없이 빌드에서 빠진다. 변수는 R G B 트리플릿(index.css). */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 레이어: canvas(바닥) → panel → raised(hover·선택·입력)
        canvas: token("canvas"),
        panel: token("panel"),
        raised: token("raised"),
        line: { DEFAULT: token("line"), strong: token("line-strong") },
        // 텍스트 3단
        ink: token("ink"),
        dim: token("dim"),
        muted: token("muted"),
        // 시세 축 (상승=빨강, 하락=파랑)
        up: token("up"),
        down: token("down"),
        // 봇 상태 축
        live: token("live"),
        warn: token("warn"),
        danger: token("danger"),

        // shadcn/ui 시맨틱 슬롯
        border: token("border"),
        background: token("background"),
        foreground: token("foreground"),
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        popover: {
          DEFAULT: token("popover"),
          foreground: token("popover-foreground"),
        },
        primary: {
          DEFAULT: token("primary"),
          foreground: token("primary-foreground"),
        },
        secondary: {
          DEFAULT: token("secondary"),
          foreground: token("secondary-foreground"),
        },
        destructive: {
          DEFAULT: token("destructive"),
          foreground: token("destructive-foreground"),
        },
        input: token("input"),
        ring: token("ring"),
      },
      borderRadius: {
        DEFAULT: "6px",
        lg: "var(--radius)",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        // 표 본문 전용 13px — 한글 종목명이 12px에선 뭉개지고 14px에선 밀도가 떨어진다
        data: ["0.8125rem", { lineHeight: "1.25rem" }],
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
        // 종목코드·타임스탬프 전용 — 웹폰트 추가 로드 없이 OS 내장 모노 사용
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
