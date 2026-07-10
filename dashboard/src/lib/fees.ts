/**
 * 매도 시 발생하는 거래수수료·제세금 계산.
 *
 * 실제 체결 거래소(KRX/NXT)는 Toss API 응답 어디에도 노출되지 않는다 —
 * Toss가 스마트 라우팅으로 내부 처리해 클라이언트는 알 수 없다. 그래서
 * 항상 KRX 요율로 추정 계산한다(NXT는 0.014%로 0.001%p 낮지만 표시
 * 목적상 차이가 무의미해 이 근사를 택함).
 */
export const KRX_COMMISSION_RATE = 0.00015;
export const SELL_TAX_RATE = 0.002;

// 컴포넌트 쪽에 동명의 <FeeBreakdown> 표시용 컴포넌트가 있어, 타입 이름을
// 겹치지 않게 SellFeeResult로 분리했다 — 나중에 이 타입을 import해서 쓰려는
// 사람이 컴포넌트와 헷갈리거나 재선언 충돌을 겪지 않도록.
export interface SellFeeResult {
  commission: number;
  tax: number;
  netAmount: number;
}

/**
 * 평가금액 기준으로 매도 시 순수령액을 추정한다.
 * evalAmount가 음수·NaN·Infinity면(백엔드 오류·계산 실수 등) 그대로 곱하면
 * 음수 수수료 같은 말이 안 되는 값이 화면에 조용히 나가버리니, 그 경우
 * 0으로 클램프하고 콘솔에 원인을 남긴다.
 */
export function calcSellFees(evalAmount: number): SellFeeResult {
  if (!Number.isFinite(evalAmount) || evalAmount < 0) {
    console.error(
      `[fees] calcSellFees: evalAmount가 유효하지 않음 (${evalAmount}) — 0으로 처리`,
    );
    return { commission: 0, tax: 0, netAmount: 0 };
  }

  const commission = evalAmount * KRX_COMMISSION_RATE;
  const tax = evalAmount * SELL_TAX_RATE;
  return {
    commission,
    tax,
    netAmount: evalAmount - commission - tax,
  };
}
