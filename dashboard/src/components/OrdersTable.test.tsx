import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { OrderItem } from "../api/types";
import { OrdersTable } from "./OrdersTable";

// 대기/완료/조건주문 3개 탭으로 status를 분류하는 필터 로직이 이 테스트의 핵심.
// 조건주문은 백엔드에 아직 order_type이 없어(LIMIT/MARKET뿐) 항상 빈 목록이어야 한다.
function makeOrder(overrides: Partial<OrderItem>): OrderItem {
  return {
    client_order_id: "c1",
    kis_order_id: null,
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
});
