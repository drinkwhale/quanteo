import type { BotStatus } from "../api/types";

export type HaltLevel = BotStatus["halt_level"];
export type Tone = "live" | "warn" | "danger";

/** Tailwind가 클래스를 정적으로 수집할 수 있도록 톤별 클래스는 전부 풀어서 적는다. */
export const TONE_CLASS: Record<
  Tone,
  { text: string; dot: string; pill: string }
> = {
  live: {
    text: "text-live",
    dot: "bg-live",
    pill: "border-live/40 bg-live/10 text-live",
  },
  warn: {
    text: "text-warn",
    dot: "bg-warn",
    pill: "border-warn/40 bg-warn/10 text-warn",
  },
  danger: {
    text: "text-danger",
    dot: "bg-danger",
    pill: "border-danger/50 bg-danger/10 text-danger",
  },
};

/** core/risk/models.py HaltLevel과 1:1 — 단계가 올라갈수록 봇이 할 수 있는 일이 줄어든다. */
export const HALT_ORDER: readonly HaltLevel[] = [
  "none",
  "reduce",
  "pause",
  "kill",
];

export const HALT_META: Record<
  HaltLevel,
  { label: string; tone: Tone; desc: string }
> = {
  none: {
    label: "가동 중",
    tone: "live",
    desc: "정상 운용. 시그널이 나오면 Risk Manager를 거쳐 주문합니다.",
  },
  reduce: {
    label: "축소 운용",
    tone: "warn",
    desc: "변동성 급등 구간. 신규 포지션 규모를 50%로 줄입니다.",
  },
  pause: {
    label: "일시정지",
    tone: "warn",
    desc: "신규 진입을 멈춥니다. 기존 포지션은 그대로 유지합니다.",
  },
  kill: {
    label: "킬 발동",
    tone: "danger",
    desc: "모든 신규 주문을 차단합니다. 손절 주문만 나갑니다.",
  },
};
