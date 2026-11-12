import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { BalanceInfo } from "../api/types";
import { AccountSummary } from "./AccountSummary";

// 과거 버그: 당일 등락 자리에 누적 수익률(profit_loss_rate)과 같은 숫자가 나왔다.
// day_change(전일 종가 기준)와 profit_loss(매입가 기준)는 서로 다른 축이라
// 표에서 열을 따로 쓴다 — 두 값이 섞이지 않는지 이 테스트가 지켜야 한다.
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
  // 상단 합계 줄은 종목별 profit_loss_rate와 우연히 같은 값이 되면
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

describe("AccountSummary 누적 손익 vs 당일 등락", () => {
  it("누적 수익률(profit_loss_rate)과 당일 등락(day_change)을 각자 열에 따로 보여준다", () => {
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    expect(screen.getByText(/7\.14%/)).toBeInTheDocument();
    expect(screen.getByText(/0\.54%/)).toBeInTheDocument();
  });

  it("day_change가 없으면(캔들 조회 실패) 누적 수익률로 조용히 대체하지 않고 결측을 표시한다", () => {
    render(<AccountSummary balance={BALANCE_WITHOUT_DAY_CHANGE} />);

    expect(screen.getByText("당일 등락 조회 실패")).toBeInTheDocument();
    // 누적 수익률은 평가손익 열 한 곳에만 있어야 한다
    expect(screen.getAllByText(/7\.14%/)).toHaveLength(1);
  });
});

describe("AccountSummary 보유 종목 표", () => {
  it("보유 수량과 평단가를 함께 보여준다", () => {
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    expect(screen.getByText("10주")).toBeInTheDocument();
    expect(screen.getByText("70,000원")).toBeInTheDocument();
  });

  it("해외 종목은 평단가를 달러로 보여준다", () => {
    render(<AccountSummary balance={BALANCE_OVERSEAS_ONLY} />);

    expect(screen.getByText("$100.00")).toBeInTheDocument();
  });

  it("주문가능금액을 못 받으면 0원이 아니라 결측(—)으로 보여준다", () => {
    const { rerender } = render(
      <AccountSummary balance={BALANCE_WITH_DAY_CHANGE} buyingPower={null} />,
    );
    expect(screen.queryByText("886,467원")).not.toBeInTheDocument();

    rerender(
      <AccountSummary balance={BALANCE_WITH_DAY_CHANGE} buyingPower="886467" />,
    );
    expect(screen.getByText("886,467원")).toBeInTheDocument();
  });

  it("조회 에러는 표 대신 에러 문구로 보여준다", () => {
    render(<AccountSummary balance={null} error="502 Bad Gateway" />);

    expect(screen.getByText(/502 Bad Gateway/)).toBeInTheDocument();
  });
});

describe("AccountSummary 수수료·세금 포함 토글", () => {
  it("토글 ON 시 평가금액뿐 아니라 수익률도 수수료 차감 기준으로 재계산된다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    expect(screen.getByText(/3\.09%/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "수수료·세금 포함" }));

    expect(screen.getByText(/2\.93%/)).toBeInTheDocument();
    expect(screen.queryByText(/3\.09%/)).not.toBeInTheDocument();
  });

  it("토글 ON 시 종목별 수익률도 수수료 차감 기준으로 재계산된다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    await user.click(screen.getByRole("button", { name: "수수료·세금 포함" }));

    expect(screen.getByText(/6\.91%/)).toBeInTheDocument();
    expect(screen.queryByText(/7\.14%/)).not.toBeInTheDocument();
  });

  it("토글을 다시 끄면 수수료 반영이 풀린다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_WITH_DAY_CHANGE} />);

    const toggle = screen.getByRole("button", { name: "수수료·세금 포함" });
    await user.click(toggle);
    expect(screen.getByText(/2\.93%/)).toBeInTheDocument();

    await user.click(toggle);
    expect(screen.getByText(/3\.09%/)).toBeInTheDocument();
    expect(screen.queryByText(/수수료 -/)).not.toBeInTheDocument();
  });

  it("해외 종목만 있으면 토글을 켜도 수수료 내역이 표시되지 않는다", async () => {
    const user = userEvent.setup();
    render(<AccountSummary balance={BALANCE_OVERSEAS_ONLY} />);

    await user.click(screen.getByRole("button", { name: "수수료·세금 포함" }));

    expect(screen.queryByText(/수수료 -/)).not.toBeInTheDocument();
  });
});
