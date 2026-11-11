/**
 * 백엔드가 Decimal 필드를 JSON 문자열로 직렬화하는 경우가 있어(TS 타입은 number로 선언되어 있어도),
 * 항상 Number()로 강제 변환한 뒤 포맷한다. 그렇지 않으면 `0 + "2895.0"` 같은 문자열 이어붙이기가
 * 조용히 발생해 화면에 숫자가 깨져 보인다.
 */
export function toNumber(n: number | string): number {
  const parsed = typeof n === "number" ? n : Number(n);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** 종목명이 캐시에 있으면 종목명을, 없으면 심볼 코드로 폴백한다. */
export function stockLabel(symbol: string, names: Map<string, string>): string {
  return names.get(symbol) ?? symbol;
}

export function fmtPrice(n: number | string, market: string): string {
  const value = toNumber(n);
  if (market === "overseas")
    return (
      // 부호는 통화 기호 앞에: "-$12.30" ("$-12.30" 아님)
      (value < 0 ? "-$" : "$") +
      Math.abs(value).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  // 원화는 정수로 — 평단가처럼 소수로 내려오는 값이 "241,605.412원"으로 찍히지 않게.
  // `|| 0`은 -0.4 같은 값이 "-0원"으로 나가는 걸 막는다.
  return (Math.round(value) || 0).toLocaleString("ko-KR") + "원";
}

/**
 * 시세 축 색상 — 국내 증시 관례대로 상승·이익=빨강(up), 하락·손실=파랑(down), 보합=회색.
 * 봇 상태 축(live/warn/danger)과는 별개라 등락·손익·매수/매도 표시는 반드시 이 헬퍼를 거친다.
 * 색만으로 구분하지 않도록 호출부는 항상 부호(+/-)가 붙은 값을 함께 보여줄 것.
 */
export function trendClass(value: number | string): string {
  const n = toNumber(value);
  return n > 0 ? "text-up" : n < 0 ? "text-down" : "text-muted";
}

/** 매수=빨강, 매도=파랑 (HTS 관례). side가 없으면(체결 방향 미상) 회색. */
export function sideClass(side: "BUY" | "SELL" | null): string {
  return side === "BUY"
    ? "text-up"
    : side === "SELL"
      ? "text-down"
      : "text-muted";
}

export const SIDE_LABEL = { BUY: "매수", SELL: "매도" } as const;

const pad2 = (n: number) => String(n).padStart(2, "0");

/** "12:27:33" — toLocaleTimeString은 환경에 따라 "13시 21분 21초"처럼 길어져 직접 조립한다. */
export function fmtClock(value: string | Date): string {
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return String(value);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/** "11.11 12:27:33" — 파싱 실패 시(예상 밖 포맷) 원본 문자열을 그대로 돌려준다. */
export function fmtStamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${pad2(d.getMonth() + 1)}.${pad2(d.getDate())} ${fmtClock(d)}`;
}

/** 국내 종목코드는 숫자로 시작하는 6자리, 해외 티커는 영문 — market 필드가 없는 응답용 추정. */
export function marketOf(symbol: string): "domestic" | "overseas" {
  return /^\d/.test(symbol) ? "domestic" : "overseas";
}

/**
 * "-6,566,989원 (10.18%)" 형식 — 등락률은 항상 절대값, 부호는 금액에만 표시.
 * rate는 Toss가 내려주는 그대로의 비율(예: -0.0905 = -9.05%)을 받는다 — 호출부에서
 * 미리 100을 곱하지 말 것. 여기서 한 번만 스케일링해야 표시값이 어긋나지 않는다.
 */
export function fmtPnl(
  amount: number | string,
  rate: number,
  market: string,
): string {
  const amt = toNumber(amount);
  const sign = amt > 0 ? "+" : "";
  return `${sign}${fmtPrice(amt, market)} (${Math.abs(rate * 100).toFixed(2)}%)`;
}

/** 지수는 원/달러 단위가 아니라 순수 포인트라 통화 기호 없이 소수점 2자리로 표시한다. */
export function fmtIndexPrice(price: number): string {
  return price.toLocaleString("ko-KR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** "-37.01 (0.45%)" 형식 — fmtPnl과 동일 규칙(부호는 변화량에만, 등락률은 절대값). */
export function fmtIndexChange(change: number, rate: number): string {
  const sign = change > 0 ? "+" : "";
  return `${sign}${fmtIndexPrice(change)} (${Math.abs(rate * 100).toFixed(2)}%)`;
}

/** "54일 22시간" / "3시간 12분" / "48초" — 큰 단위 두 개까지만 보여준다. */
export function fmtUptime(seconds: number): string {
  const d = Math.floor(seconds / 86_400);
  const h = Math.floor((seconds % 86_400) / 3_600);
  const m = Math.floor((seconds % 3_600) / 60);
  if (d > 0) return `${d}일 ${h}시간`;
  if (h > 0) return `${h}시간 ${m}분`;
  if (m > 0) return `${m}분`;
  return `${Math.floor(seconds)}초`;
}
