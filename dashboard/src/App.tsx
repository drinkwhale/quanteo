import { useMemo, useState } from "react";
import { RotateCw } from "lucide-react";
import { AccountSummary } from "./components/AccountSummary";
import { ControlPanel } from "./components/ControlPanel";
import { IndicesStrip } from "./components/IndicesStrip";
import { MarketStocksTable } from "./components/MarketStocksTable";
import { OrdersAndFillsPanel } from "./components/OrdersAndFillsPanel";
import { Panel } from "./components/Panel";
import { StatusBar } from "./components/StatusBar";
import { StreamConnectionBadge, StreamLog } from "./components/StreamLog";
import { TabNav } from "./components/TabNav";
import { useBalance } from "./hooks/useBalance";
import { useFills } from "./hooks/useFills";
import { useIndices } from "./hooks/useIndices";
import { useMarketStocks } from "./hooks/useMarketStocks";
import { useOrders } from "./hooks/useOrders";
import { usePositions } from "./hooks/usePositions";
import { useStatus } from "./hooks/useStatus";
import { useStockNames } from "./hooks/useStockNames";
import { useStream } from "./hooks/useStream";
import { StrategyPage } from "./pages/Strategy";
import { StockDetail } from "./pages/StockDetail";

export default function App() {
  const [activeTab, setActiveTab] = useState<"ops" | "chart">("ops");

  const { status, refetch: refetchStatus } = useStatus(3000);
  const { positions, total: posTotal, error: posError } = usePositions(5000);
  const {
    balance,
    error: balanceError,
    lastUpdated: balanceUpdatedAt,
  } = useBalance(2000);
  const { indices, error: indicesError } = useIndices(30000);
  const {
    stocks: marketStocks,
    sortBy: marketSortBy,
    setSortBy: setMarketSortBy,
    isLoading: marketLoading,
    error: marketError,
  } = useMarketStocks(30000);
  const {
    orders,
    total: ordTotal,
    error: ordError,
    refetch: refetchOrders,
  } = useOrders(5000);
  const { fills, total: fillTotal, error: fillError } = useFills(10000);
  const { logs, connected } = useStream();

  // 종목 코드 대신 종목명을 보여주기 위한 심볼 → 이름 매핑 (전 패널 공유 캐시)
  const allSymbols = useMemo(
    () => [
      ...positions.map((p) => p.symbol),
      ...orders.map((o) => o.symbol),
      ...fills.map((f) => f.symbol),
    ],
    [positions, orders, fills],
  );
  const stockNames = useStockNames(allSymbols);

  const tabs = [
    { id: "ops", label: "운용현황" },
    { id: "chart", label: "종목상세" },
  ];

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      <StatusBar status={status} streamConnected={connected} />

      <TabNav
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={(id) => setActiveTab(id as "ops" | "chart")}
      />

      <main className="flex-1 p-4 space-y-6">
        {activeTab === "ops" && (
          <>
            <Panel title="주요 지수·환율">
              <IndicesStrip indices={indices} error={indicesError} />
            </Panel>

            <Panel
              title="주요 종목"
              headerExtra={
                <div className="flex gap-1">
                  {(
                    [
                      { id: "trading_value", label: "거래대금" },
                      { id: "volume", label: "거래량" },
                      { id: "uptrend", label: "급상승" },
                      { id: "downtrend", label: "급하락" },
                    ] as const
                  ).map((btn) => (
                    <button
                      key={btn.id}
                      type="button"
                      onClick={() =>
                        setMarketSortBy(
                          btn.id as
                            | "trading_value"
                            | "volume"
                            | "uptrend"
                            | "downtrend",
                        )
                      }
                      className={`px-2.5 py-1 text-xs rounded font-medium transition-colors ${
                        marketSortBy === btn.id
                          ? "bg-accent text-surface"
                          : "bg-muted/10 text-muted hover:bg-muted/20"
                      }`}
                    >
                      {btn.label}
                    </button>
                  ))}
                </div>
              }
            >
              <MarketStocksTable
                stocks={marketStocks}
                error={marketError}
                isLoading={marketLoading}
              />
            </Panel>

            {/* 운영 현황 — 포지션·주문·체결·이벤트를 탭 전환 없이 동시 노출 */}
            <section
              aria-labelledby="ops-heading"
              className="flex flex-col xl:flex-row gap-4"
            >
              <h2 id="ops-heading" className="sr-only">
                운영 현황
              </h2>

              <div className="flex-1 min-w-0 space-y-4">
                <Panel
                  title="주문·체결"
                  headerExtra={
                    <button
                      type="button"
                      onClick={refetchOrders}
                      className="p-1.5 rounded hover:bg-accent/10 transition-colors"
                      title="새로고침"
                      aria-label="주문·체결 새로고침"
                    >
                      <RotateCw className="w-4 h-4 text-muted hover:text-accent" />
                    </button>
                  }
                >
                  <OrdersAndFillsPanel
                    orders={orders}
                    fills={fills}
                    ordersError={ordError}
                    fillsError={fillError}
                    ordersTotal={ordTotal}
                    fillsTotal={fillTotal}
                    onRefetch={refetchOrders}
                    stockNames={stockNames}
                  />
                </Panel>

                <Panel
                  title="실시간 이벤트"
                  headerExtra={<StreamConnectionBadge connected={connected} />}
                >
                  <StreamLog logs={logs} />
                </Panel>
              </div>

              {/*
                왼쪽 목록이 훨씬 길어도 오른쪽에 빈 배경만 남지 않도록, 사이드바 자체를
                border-l로 경계를 그린 레일로 만든다 — flex 기본 stretch로 레일이
                왼쪽 컬럼과 같은 높이까지 늘어나고, 안의 내용만 sticky로 위쪽에 고정된다.
              */}
              <aside className="w-full xl:w-80 xl:flex-shrink-0 xl:border-l xl:border-border xl:pl-4">
                <div className="space-y-4 xl:sticky xl:top-14">
                  <Panel title="계좌 요약">
                    <AccountSummary
                      balance={balance}
                      error={balanceError}
                      lastUpdated={balanceUpdatedAt}
                    />
                  </Panel>

                  <Panel title="봇 제어">
                    <ControlPanel status={status} onAction={refetchStatus} />
                  </Panel>
                </div>
              </aside>
            </section>

            {/* 전략 분석 — CCI·신뢰도·백테스트 등 지표 패널을 별도 섹션으로 분리 */}
            <section aria-labelledby="strategy-heading" className="space-y-4">
              <h2
                id="strategy-heading"
                className="text-xs font-sans font-semibold text-muted tracking-wider border-t border-border pt-4"
              >
                전략 분석
              </h2>
              <StrategyPage
                logs={logs}
                positions={positions}
                stockNames={stockNames}
                onKill={refetchStatus}
              />
            </section>
          </>
        )}

        {activeTab === "chart" && <StockDetail recentSymbols={allSymbols} />}
      </main>
    </div>
  );
}
