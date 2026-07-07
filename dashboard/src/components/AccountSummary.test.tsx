import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { BalanceInfo } from "../api/types";
import { AccountSummary } from "./AccountSummary";

// 이번에 고친 버그: "현재가" 토글이 평가금액 모드와 같은 숫자(profit_loss_rate)를
// 보여주고 있었다. day_change(오늘 시가 기준)와 profit_loss(매입가 기준)가
// 서로 다른 축으로 정확히 분기되는지 이 테스트가 지켜야 한다.
const BALANCE_WITH_DAY_CHANGE: BalanceInfo = {
  items: [
    {
      symbol: "005930",
      symbol_name: "삼성전자",
      qty: 10,
      avg_price: 70000,
      current_price: 75000,
      eval_amount: 750000,
      profit_loss: 50000,
      profit_loss_rate: 0.0714,
      day_change: { amount: 400, rate: 0.00536 },
      market: "domestic",
    },
  ],
  // 상단 "내 투자" 합계는 종목별 profit_loss_rate와 우연히 같은 값이 되면
  // 안 된다 — 아래 테스트가 "합계 줄" vs "종목 줄"을 헷갈려 통과하는 걸
  // 막기 위해 의도적으로 다른 비율(3.09%)이 나오게 한다.
  total_eval_amount_krw: 1000000,
  total_profit_loss_krw: 30000,
  deposit: 0,
};

const BALANCE_WITHOUT_DAY_CHANGE: BalanceInfo = {
  ...BALANCE_WITH_DAY_CHANGE,
  items: [{ ...BALANCE_WITH_DAY_CHANGE.items[0], day_change: null }],
};

describe("AccountSummary 현재가/평가금액 토글", () => {
  it("평가금액 모드에서는 매입가 기준 누적 수익률(profit_loss_rate)을 보여준다", () => {
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);
    // profit_loss=50000, rate=0.0714 → "+50,000원 (7.14%)"
    expect(screen.getByText(/7\.14%/)).toBeInTheDocument();
  });

  it("현재가 모드로 바꾸면 매입가 수익률이 아니라 오늘 시가 기준 등락(day_change)을 보여준다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    await user.click(screen.getByRole("button", { name: "현재가" }));

    // day_change.rate=0.00536 → "0.54%" — profit_loss_rate(7.14%)와 달라야 한다.
    expect(screen.getByText(/0\.54%/)).toBeInTheDocument();
    expect(screen.queryByText(/7\.14%/)).not.toBeInTheDocument();
  });

  it("day_change가 없으면(캔들 조회 실패) 매입가 수익률로 조용히 대체하지 않고 결측을 표시한다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITHOUT_DAY_CHANGE} />);

    await user.click(screen.getByRole("button", { name: "현재가" }));

    expect(screen.getByText("당일 등락 조회 실패")).toBeInTheDocument();
    expect(screen.queryByText(/7\.14%/)).not.toBeInTheDocument();
  });
});
