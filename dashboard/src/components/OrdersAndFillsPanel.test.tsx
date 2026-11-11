import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { OrderItem } from "../api/types";
import { OrdersAndFillsPanel } from "./OrdersAndFillsPanel";

vi.mock("../api/client", () => ({
  api: { cancelOrder: vi.fn() },
}));

function order(overrides: Partial<OrderItem>): OrderItem {
  return {
    client_order_id: "c-1",
    broker_order_id: "b-1",
    symbol: "005930",
    market: "domestic",
    env: "vps",
    side: "BUY",
    order_type: "limit",
    qty: 10,
    price: 70000,
    status: "submitted",
    created_at: "2026-11-11T09:00:00+09:00",
    updated_at: "2026-11-11T09:00:00+09:00",
    ...overrides,
  };
}

const NAMES = new Map([["005930", "삼성전자"]]);

function renderPanel(
  props: Partial<Parameters<typeof OrdersAndFillsPanel>[0]>,
) {
  return render(
    <OrdersAndFillsPanel
      orders={[]}
      fills={[]}
      fillsTotal={0}
      stockNames={NAMES}
      {...props}
    />,
  );
}

describe("OrdersAndFillsPanel", () => {
  beforeEach(() => {
    vi.mocked(api.cancelOrder).mockReset();
  });

  it("주문을 상태에 따라 미체결/완료로 나눠 보여준다", async () => {
    const user = userEvent.setup();
    renderPanel({
      orders: [
        order({ client_order_id: "open", status: "partial" }),
        order({ client_order_id: "done", status: "filled", side: "SELL" }),
      ],
    });

    // 미체결 탭: 부분체결 주문만
    expect(screen.getByText("부분체결")).toBeInTheDocument();
    expect(screen.getByText("매수")).toBeInTheDocument();
    expect(screen.queryByText("매도")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /완료/ }));
    expect(screen.getByText("매도")).toBeInTheDocument();
    expect(screen.queryByText("부분체결")).not.toBeInTheDocument();
    // 완료된 주문에는 취소 버튼이 없다
    expect(screen.queryByRole("button", { name: "주문 취소" })).toBeNull();
  });

  it("주문 취소 → broker_order_id로 API 호출 후 목록을 다시 읽는다", async () => {
    vi.mocked(api.cancelOrder).mockResolvedValue({
      success: true,
      order_id: "b-1",
      message: "주문 취소 완료",
    });
    const user = userEvent.setup();
    const onRefetch = vi.fn();
    renderPanel({ orders: [order({})], onRefetch });

    await user.click(screen.getByRole("button", { name: "주문 취소" }));

    await waitFor(() => expect(api.cancelOrder).toHaveBeenCalledWith("b-1"));
    expect(onRefetch).toHaveBeenCalledTimes(1);
  });

  it("취소가 실패하면 에러를 보여주고 주문은 목록에 그대로 둔다", async () => {
    vi.mocked(api.cancelOrder).mockRejectedValue(new Error("400 이미 체결됨"));
    const user = userEvent.setup();
    renderPanel({ orders: [order({})] });

    await user.click(screen.getByRole("button", { name: "주문 취소" }));

    await waitFor(() =>
      expect(screen.getByText(/400 이미 체결됨/)).toBeInTheDocument(),
    );
    const table = screen.getByRole("table");
    expect(within(table).getByText("삼성전자")).toBeInTheDocument();
  });

  it("조회가 실패했으면 '주문이 없습니다'라고 말하지 않는다", () => {
    renderPanel({ ordersError: "500 Internal Server Error" });

    expect(screen.getByText(/500 Internal Server Error/)).toBeInTheDocument();
    expect(screen.queryByText(/미체결 주문이 없습니다/)).toBeNull();
  });
});
