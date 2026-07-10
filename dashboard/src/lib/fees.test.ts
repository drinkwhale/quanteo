import { describe, expect, it, vi } from "vitest";
import { calcSellFees, KRX_COMMISSION_RATE, SELL_TAX_RATE } from "./fees";

describe("calcSellFees", () => {
  it("KRX 요율대로 수수료·세금을 계산한다", () => {
    const result = calcSellFees(1_000_000);

    expect(result.commission).toBeCloseTo(1_000_000 * KRX_COMMISSION_RATE);
    expect(result.tax).toBeCloseTo(1_000_000 * SELL_TAX_RATE);
  });

  it("netAmount은 평가금액에서 수수료·세금을 뺀 값이다", () => {
    const result = calcSellFees(1_000_000);

    expect(result.netAmount).toBeCloseTo(
      1_000_000 - result.commission - result.tax,
    );
  });

  it("평가금액이 0이면 모든 값이 0이다", () => {
    const result = calcSellFees(0);

    expect(result).toEqual({ commission: 0, tax: 0, netAmount: 0 });
  });

  it("음수 평가금액은 0으로 클램프하고 콘솔에 에러를 남긴다", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const result = calcSellFees(-100);

    expect(result).toEqual({ commission: 0, tax: 0, netAmount: 0 });
    expect(errorSpy).toHaveBeenCalledOnce();

    errorSpy.mockRestore();
  });

  it("NaN·Infinity 평가금액도 0으로 클램프한다", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(calcSellFees(NaN)).toEqual({
      commission: 0,
      tax: 0,
      netAmount: 0,
    });
    expect(calcSellFees(Infinity)).toEqual({
      commission: 0,
      tax: 0,
      netAmount: 0,
    });

    errorSpy.mockRestore();
  });
});
