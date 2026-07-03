/**
 * 백엔드가 Decimal 필드를 JSON 문자열로 직렬화하는 경우가 있어(TS 타입은 number로 선언되어 있어도),
 * 항상 Number()로 강제 변환한 뒤 포맷한다. 그렇지 않으면 `0 + "2895.0"` 같은 문자열 이어붙이기가
 * 조용히 발생해 화면에 숫자가 깨져 보인다.
 */
export function toNumber(n: number | string): number {
  const parsed = typeof n === "number" ? n : Number(n);
  return Number.isFinite(parsed) ? parsed : 0;
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
