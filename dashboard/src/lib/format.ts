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
      "$" +
      value.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  return value.toLocaleString("ko-KR") + "원";
}

/**
 * 국내 증시 평가손익 색상 관례: 상승(이익)=빨강, 하락(손실)=파랑.
 * 대시보드 다른 곳의 positive(초록)/negative(빨강)는 "봇 상태"를 뜻하는 별개 축이라
 * 여기 그대로 쓰면 반대 의미가 된다 — 평가손익 표시는 반드시 이 헬퍼를 통해서만.
 */
export function pnlColorClass(value: number | string): string {
  return toNumber(value) < 0 ? "text-accent" : "text-negative";
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
