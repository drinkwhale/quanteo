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

export interface FeeBreakdown {
  commission: number;
  tax: number;
  netAmount: number;
}

/** 평가금액 기준으로 매도 시 순수령액을 추정한다. */
export function calcSellFees(evalAmount: number): FeeBreakdown {
  const commission = evalAmount * KRX_COMMISSION_RATE;
  const tax = evalAmount * SELL_TAX_RATE;
  return {
    commission,
    tax,
    netAmount: evalAmount - commission - tax,
  };
}
