import { useState } from "react";
import { ControlPanel } from "./components/ControlPanel";
import { FillsTable } from "./components/FillsTable";
import { OrdersTable } from "./components/OrdersTable";
import { PositionsTable } from "./components/PositionsTable";
import { StatusBar } from "./components/StatusBar";
import { StreamLog } from "./components/StreamLog";
import { useFills } from "./hooks/useFills";
import { useOrders } from "./hooks/useOrders";
import { usePositions } from "./hooks/usePositions";
import { useStatus } from "./hooks/useStatus";
import { useStream } from "./hooks/useStream";

type Tab = "positions" | "orders" | "fills";

export default function App() {
  const { status, refetch: refetchStatus } = useStatus(3000);
  const { positions, total: posTotal, error: posError } = usePositions(5000);
  const {
    orders,
    total: ordTotal,
    error: ordError,
    refetch: refetchOrders,
  } = useOrders(5000);
  const { fills, total: fillTotal, error: fillError } = useFills(10000);
  const { logs, connected } = useStream();

  const [tab, setTab] = useState<Tab>("positions");

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      <StatusBar status={status} streamConnected={connected} />

      <main className="flex-1 p-4 grid grid-cols-1 xl:grid-cols-3 gap-4 auto-rows-min">
        {/* 왼쪽 2/3: 탭 패널 */}
        <div className="xl:col-span-2 space-y-4">
          {/* 탭 헤더 */}
          <div className="flex gap-1 border-b border-border">
            {(
              [
                { key: "positions", label: "포지션" },
                { key: "orders", label: "주문" },
                { key: "fills", label: "체결" },
              ] as { key: Tab; label: string }[]
            ).map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`px-4 py-2 text-sm font-mono transition-colors border-b-2 -mb-px ${
                  tab === key
                    ? "border-accent text-white"
                    : "border-transparent text-muted hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* 탭 콘텐츠 */}
          {tab === "positions" && (
            <PositionsTable
              positions={positions}
              total={posTotal}
              error={posError}
            />
          )}
          {tab === "orders" && (
            <OrdersTable
              orders={orders}
              total={ordTotal}
              error={ordError}
              onRefetch={refetchOrders}
            />
          )}
          {tab === "fills" && (
            <FillsTable fills={fills} total={fillTotal} error={fillError} />
          )}

          <StreamLog logs={logs} connected={connected} />
        </div>

        {/* 오른쪽 1/3: 제어 패널 */}
        <div className="space-y-4">
          <ControlPanel status={status} onAction={refetchStatus} />
        </div>
      </main>
    </div>
  );
}
