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

// KRX_COMMISSION_RATE(0.015%) + SELL_TAX_RATE(0.2%) 적용 시 예상 수치:
// domestic eval_amount=750,000 → commission=112.5, tax=1,500, 합계 1,612.5
// 총합: totalPnl(30,000) - 1,612.5 = 28,387.5, costBasis=970,000 → 2.93%
// 종목: profit_loss(50,000) - 1,612.5 = 48,387.5, costBasis=700,000 → 6.91%
const BALANCE_OVERSEAS_ONLY: BalanceInfo = {
  items: [
    {
      symbol: "AAPL",
      symbol_name: "애플",
      qty: 5,
      avg_price: 100,
      current_price: 110,
      eval_amount: 550,
      profit_loss: 50,
      profit_loss_rate: 0.1,
      day_change: null,
      market: "overseas",
    },
  ],
  total_eval_amount_krw: 700000,
  total_profit_loss_krw: 50000,
  deposit: 0,
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

describe("AccountSummary 종목 서브텍스트 (보유수량 vs 평단가)", () => {
  it("평가금액 모드에서는 보유 수량을 보여준다", () => {
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);
    expect(screen.getByText("10주")).toBeInTheDocument();
  });

  it("현재가 모드로 바꾸면 보유 수량 대신 1주 평균(평단가)을 보여준다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    await user.click(screen.getByRole("button", { name: "현재가" }));

    expect(screen.getByText("평단 70,000원")).toBeInTheDocument();
    expect(screen.queryByText("10주")).not.toBeInTheDocument();
  });

  it("해외 종목은 현재가 모드에서 평단가를 달러로 보여준다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_OVERSEAS_ONLY} />);

    await user.click(screen.getByRole("button", { name: "현재가" }));

    expect(screen.getByText("평단 $100.00")).toBeInTheDocument();
  });
});

describe("AccountSummary 수수료·세금 포함 토글", () => {
  it("현재가 모드에서는 토글 버튼이 보이지 않는다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    await user.click(screen.getByRole("button", { name: "현재가" }));

    expect(
      screen.queryByRole("button", { name: "수수료·세금 포함" }),
    ).not.toBeInTheDocument();
  });

  it("토글 ON 시 평가금액뿐 아니라 수익률도 수수료 차감 기준으로 재계산된다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    // 토글 전: 원래 수익률(3.09%)이 보여야 한다.
    expect(screen.getByText(/3\.09%/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "수수료·세금 포함" }));

    // 토글 후: 총합 수익률이 28,387.5 / 970,000 = 2.93%로 바뀌어야 한다 —
    // 평가금액만 줄고 수익률은 그대로면(3.09%) 앞뒤가 안 맞는 화면이다.
    expect(screen.getByText(/2\.93%/)).toBeInTheDocument();
    expect(screen.queryByText(/3\.09%/)).not.toBeInTheDocument();
  });

  it("토글 ON 시 종목별 수익률도 수수료 차감 기준으로 재계산된다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    await user.click(screen.getByRole("button", { name: "수수료·세금 포함" }));

    // 종목: (50,000 - 1,612.5) / 700,000 = 6.91% — 원래 7.14%와 달라야 한다.
    expect(screen.getByText(/6\.91%/)).toBeInTheDocument();
    expect(screen.queryByText(/7\.14%/)).not.toBeInTheDocument();
  });

  it("토글 ON 상태에서 현재가 모드로 바꾸면 수수료 반영이 풀리고 버튼도 사라진다(고친 버그 회귀 테스트)", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    await user.click(screen.getByRole("button", { name: "수수료·세금 포함" }));
    expect(screen.getByText(/2\.93%/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "현재가" }));

    // 이전 버그: 토글 버튼은 숨겨지는데 총합 숫자는 수수료 반영 상태로
    // 붙박여 남아 있었다 — 이제는 원래 수익률(3.09%)로 돌아가야 한다.
    expect(screen.queryByText(/2\.93%/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "수수료·세금 포함" }),
    ).not.toBeInTheDocument();

    // 평가금액 모드로 돌아오면 토글 상태(ON)가 유지돼 있었으니 다시 수수료가
    // 반영된 2.93%로 보여야 한다 — 상태 자체를 잃어버리는 것과는 다른 문제다.
    await user.click(screen.getByRole("button", { name: "평가금액" }));
    expect(screen.getByText(/2\.93%/)).toBeInTheDocument();
  });

  it("해외 종목만 있으면 토글을 켜도 수수료 내역이 표시되지 않는다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_OVERSEAS_ONLY} />);

    await user.click(screen.getByRole("button", { name: "수수료·세금 포함" }));

    expect(screen.queryByText(/수수료 -/)).not.toBeInTheDocument();
  });
});
