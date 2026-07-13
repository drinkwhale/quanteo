import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { OrderItem, OrderStatus } from "../api/types";
import { OrdersTable } from "./OrdersTable";

// 대기/완료/조건주문 3개 탭으로 status를 분류하는 필터 로직이 이 테스트의 핵심.
// 조건주문은 백엔드에 아직 order_type이 없어(LIMIT/MARKET뿐) 항상 빈 목록이어야 한다.
function makeOrder(overrides: Partial<OrderItem>): OrderItem {
  return {
    client_order_id: "c1",
    broker_order_id: null,
    symbol: "005930",
    market: "domestic",
    env: "vps",
    side: "BUY",
    order_type: "LIMIT",
    qty: 1,
    price: 70000,
    status: "pending",
    created_at: "2026-07-13T09:00:00Z",
    updated_at: "2026-07-13T09:00:00Z",
    ...overrides,
  };
}

const ORDERS: OrderItem[] = [
  makeOrder({ client_order_id: "pending-1", status: "pending" }),
  makeOrder({ client_order_id: "filled-1", status: "filled" }),
  makeOrder({ client_order_id: "cancelled-1", status: "cancelled" }),
];

describe("OrdersTable tabs", () => {
  it("기본 탭(대기)에서는 대기 상태 주문만 보인다", () => {
    render(<OrdersTable orders={ORDERS} stockNames={new Map()} />);

    expect(screen.getByRole("tab", { name: /대기/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getAllByRole("row")).toHaveLength(2); // header + pending-1
  });

  it("완료 탭을 누르면 filled/cancelled 주문이 보인다", async () => {
    const user = userEvent.setup();
    render(<OrdersTable orders={ORDERS} stockNames={new Map()} />);

    await user.click(screen.getByRole("tab", { name: /완료/ }));

    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3); // header + filled-1 + cancelled-1
  });

  it("조건주문 탭은 데이터가 없어 항상 빈 상태를 보여준다", async () => {
    const user = userEvent.setup();
    render(<OrdersTable orders={ORDERS} stockNames={new Map()} />);

    await user.click(screen.getByRole("tab", { name: /조건주문/ }));

    expect(
      screen.getByText("조건주문 기능은 아직 지원되지 않음"),
    ).toBeInTheDocument();
  });

  it("탭 배지가 상태별 건수를 정확히 보여준다", () => {
    render(<OrdersTable orders={ORDERS} stockNames={new Map()} />);

    expect(screen.getByRole("tab", { name: /대기/ })).toHaveTextContent("1");
    expect(screen.getByRole("tab", { name: /완료/ })).toHaveTextContent("2");
    expect(screen.getByRole("tab", { name: /조건주문/ })).toHaveTextContent(
      "0",
    );
  });

  // submitted/partial은 CANCELLABLE_STATUSES에 있는데도 대기 탭에서 취소
  // 버튼이 안 뜨던 회귀 — partial이 CANCELLABLE_STATUSES에서 빠져있던 버그를
  // 이 테스트가 잡는다.
  it("submitted/partial 주문은 대기 탭에서 취소 버튼이 보인다", () => {
    const orders: OrderItem[] = [
      makeOrder({
        client_order_id: "submitted-1",
        status: "submitted",
        broker_order_id: "broker-1",
      }),
      makeOrder({
        client_order_id: "partial-1",
        status: "partial",
        broker_order_id: "broker-2",
      }),
    ];
    render(<OrdersTable orders={orders} stockNames={new Map()} />);

    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3); // header + 2
    expect(
      within(rows[1]).getByRole("button", { name: /취소/ }),
    ).toBeInTheDocument();
    expect(
      within(rows[2]).getByRole("button", { name: /취소/ }),
    ).toBeInTheDocument();
  });

  it("완료 탭(filled/cancelled/rejected)에는 취소 버튼이 없다", async () => {
    const user = userEvent.setup();
    const orders: OrderItem[] = [
      makeOrder({
        client_order_id: "filled-1",
        status: "filled",
        broker_order_id: "broker-1",
      }),
      makeOrder({
        client_order_id: "rejected-1",
        status: "rejected",
        broker_order_id: "broker-2",
      }),
    ];
    render(<OrdersTable orders={orders} stockNames={new Map()} />);

    await user.click(screen.getByRole("tab", { name: /완료/ }));

    expect(
      screen.queryByRole("button", { name: /취소/ }),
    ).not.toBeInTheDocument();
  });

  it("알 수 없는 status는 어느 탭에도 안 뜨고 콘솔 경고만 남긴다", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const orders = [
      makeOrder({
        client_order_id: "mystery-1",
        // 백엔드가 아직 프론트에 반영 안 된 새 status를 내려보내는 상황을
        // 흉내낸다 — 런타임에는 타입이 강제되지 않으므로 실제로 벌어질 수 있다.
        status: "expired" as unknown as OrderStatus,
      }),
    ];
    render(<OrdersTable orders={orders} stockNames={new Map()} />);

    expect(screen.getByRole("tab", { name: /대기/ })).toHaveTextContent("0");
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("mystery-1"));

    warnSpy.mockRestore();
  });

  // 회귀 테스트 — side가 BUY/SELL 값에 따라 실제로 다르게 표시되는지 확인한다.
  // 과거 API가 side를 소문자("buy")로 내려보내면서 o.side === "BUY" 비교가
  // 항상 false가 되어 모든 주문이 SELL로 잘못 표시되던 버그가 있었다.
  it("side에 따라 방향 텍스트와 색상이 다르게 표시된다", () => {
    const orders: OrderItem[] = [
      makeOrder({ client_order_id: "buy-1", side: "BUY" }),
      makeOrder({ client_order_id: "sell-1", side: "SELL" }),
    ];
    render(<OrdersTable orders={orders} stockNames={new Map()} />);

    const buyCell = screen.getByText("BUY");
    const sellCell = screen.getByText("SELL");
    expect(buyCell).toHaveClass("text-positive");
    expect(sellCell).toHaveClass("text-negative");
  });
});
