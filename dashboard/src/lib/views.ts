export type ViewId = "desk" | "chart" | "bot" | "watchlist";

/** 화면 목록 — id는 URL 해시(#desk 등)로 그대로 쓰인다. */
export const VIEWS: readonly { id: ViewId; label: string }[] = [
  { id: "desk", label: "운용" },
  { id: "chart", label: "차트" },
  { id: "bot", label: "전략·봇" },
  { id: "watchlist", label: "관심종목" },
];
