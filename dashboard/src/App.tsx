import { AccountSummary } from "./components/AccountSummary";
import { ControlPanel } from "./components/ControlPanel";
import { FillsTable } from "./components/FillsTable";
import { OrdersTable } from "./components/OrdersTable";
import { Panel } from "./components/Panel";
import { PositionsTable } from "./components/PositionsTable";
import { StatusBar } from "./components/StatusBar";
import { StreamConnectionBadge, StreamLog } from "./components/StreamLog";
import { useFills } from "./hooks/useFills";
import { useOrders } from "./hooks/useOrders";
import { usePositions } from "./hooks/usePositions";
import { useStatus } from "./hooks/useStatus";
import { useStream } from "./hooks/useStream";
import { StrategyPage } from "./pages/Strategy";

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

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      <StatusBar status={status} streamConnected={connected} />

      <main className="flex-1 p-4 space-y-6">
        {/* 운영 현황 — 포지션·주문·체결·이벤트를 탭 전환 없이 동시 노출 */}
        <section
          aria-labelledby="ops-heading"
          className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start"
        >
          <h2 id="ops-heading" className="sr-only">
            운영 현황
          </h2>

          <div className="xl:col-span-2 space-y-4">
            <Panel title="포지션" badge={`${posTotal}건`}>
              <PositionsTable positions={positions} error={posError} />
            </Panel>

            <Panel title="주문내역" badge={`${ordTotal}건`}>
              <OrdersTable
                orders={orders}
                error={ordError}
                onRefetch={refetchOrders}
              />
            </Panel>

            <Panel title="체결내역" badge={`${fillTotal}건`}>
              <FillsTable fills={fills} error={fillError} />
            </Panel>

            <Panel
              title="실시간 이벤트"
              headerExtra={<StreamConnectionBadge connected={connected} />}
            >
              <StreamLog logs={logs} />
            </Panel>
          </div>

          <div className="space-y-4 xl:sticky xl:top-14 self-start">
            <Panel title="계좌 요약">
              <AccountSummary positions={positions} />
            </Panel>

            <Panel title="봇 제어">
              <ControlPanel status={status} onAction={refetchStatus} />
            </Panel>
          </div>
        </section>

        {/* 전략 분석 — CCI·신뢰도·백테스트 등 지표 패널을 별도 섹션으로 분리 */}
        <section aria-labelledby="strategy-heading" className="space-y-4">
          <h2
            id="strategy-heading"
            className="text-xs font-mono font-semibold text-muted tracking-wider border-t border-border pt-4"
          >
            전략 분석
          </h2>
          <StrategyPage
            logs={logs}
            positions={positions}
            onKill={refetchStatus}
          />
        </section>
      </main>
    </div>
  );
}
