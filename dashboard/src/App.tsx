import { useMemo, useState } from "react";
import { RotateCw } from "lucide-react";
import { AccountSummary } from "./components/AccountSummary";
import { ControlPanel } from "./components/ControlPanel";
import { IndicesStrip } from "./components/IndicesStrip";
import { MarketStocksTable } from "./components/MarketStocksTable";
import { OrdersAndFillsPanel } from "./components/OrdersAndFillsPanel";
import { StatusBar } from "./components/StatusBar";
import { TabNav } from "./components/TabNav";
import { useBalance } from "./hooks/useBalance";
import { useFills } from "./hooks/useFills";
import { useGridLayout } from "./hooks/useGridLayout";
import { useIndices } from "./hooks/useIndices";
import { useMarketStocks } from "./hooks/useMarketStocks";
import { useOrders } from "./hooks/useOrders";
import { usePositions } from "./hooks/usePositions";
import { useStatus } from "./hooks/useStatus";
import { useStockNames } from "./hooks/useStockNames";
import { useStream } from "./hooks/useStream";
import { RndPanel } from "./components/RndPanel";
import { StrategyPage } from "./pages/Strategy";
import { StockDetail } from "./pages/StockDetail";

export default function App() {
  const [activeTab, setActiveTab] = useState<"ops" | "chart">("ops");
  const { positions, updatePosition, resetLayout, mounted } = useGridLayout();

  const { status, refetch: refetchStatus } = useStatus(3000);
  const { positions: portfolioPositions } = usePositions(5000);
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
      ...portfolioPositions.map((p) => p.symbol),
      ...orders.map((o) => o.symbol),
      ...fills.map((f) => f.symbol),
    ],
    [portfolioPositions, orders, fills],
  );
  const stockNames = useStockNames(allSymbols);
  const uniqueRecentSymbols = useMemo(
    () => Array.from(new Set(allSymbols)),
    [allSymbols],
  );

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

      <main className="flex-1 flex flex-col">
        {/* 리셋 버튼 (우측 상단) */}
        {activeTab === "ops" && mounted && (
          <div className="px-4 pt-4 pb-2 flex justify-end">
            <button
              onClick={resetLayout}
              className="px-3 py-1.5 text-xs font-medium bg-muted/10 text-muted hover:bg-muted/20 rounded transition-colors"
              title="대시보드 레이아웃 리셋"
            >
              레이아웃 리셋
            </button>
          </div>
        )}

        <div
          className="flex-1 overflow-auto relative"
          style={{ height: "100%", position: "relative" }}
        >
          {activeTab === "ops" && mounted && (
            <div
              style={{ position: "relative", width: "100%", height: "100%" }}
            >
              {/* 지수·환율 */}
              <RndPanel
                id="indices"
                title="주요 지수·환율"
                position={positions.indices}
                onPositionChange={updatePosition}
              >
                <IndicesStrip indices={indices} error={indicesError} />
              </RndPanel>

              {/* 주요 종목 */}
              <RndPanel
                id="market-stocks"
                title="주요 종목"
                position={positions["market-stocks"]}
                onPositionChange={updatePosition}
                headerExtra={
                  <div className="flex gap-1 flex-wrap">
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
                  stockNames={stockNames}
                />
              </RndPanel>

              {/* 계좌요약 */}
              <RndPanel
                id="account-summary"
                title="계좌 요약"
                position={positions["account-summary"]}
                onPositionChange={updatePosition}
              >
                <AccountSummary
                  balance={balance}
                  error={balanceError}
                  lastUpdated={balanceUpdatedAt}
                />
              </RndPanel>

              {/* 주문·체결 */}
              <RndPanel
                id="operations"
                title="주문·체결"
                position={positions.operations}
                onPositionChange={updatePosition}
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
              </RndPanel>

              {/* 봇 제어 */}
              <RndPanel
                id="control"
                title="봇 제어"
                position={positions.control}
                onPositionChange={updatePosition}
              >
                <ControlPanel status={status} onAction={refetchStatus} />
              </RndPanel>

              {/* 전략 분석 */}
              <RndPanel
                id="strategy"
                title="전략 분석"
                position={positions.strategy}
                onPositionChange={updatePosition}
              >
                <StrategyPage
                  logs={logs}
                  positions={portfolioPositions}
                  stockNames={stockNames}
                  onKill={refetchStatus}
                />
              </RndPanel>
            </div>
          )}

          {/* Chart 탭 */}
          {activeTab === "chart" && (
            <div className="p-4">
              <StockDetail recentSymbols={uniqueRecentSymbols} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
