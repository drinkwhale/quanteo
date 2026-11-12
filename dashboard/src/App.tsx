import { useMemo, useSyncExternalStore } from "react";
import { api } from "./api/client";
import { AccountSummary } from "./components/AccountSummary";
import { AppHeader } from "./components/AppHeader";
import { IndicesStrip } from "./components/IndicesStrip";
import { MarketStocksTable } from "./components/MarketStocksTable";
import { OrdersAndFillsPanel } from "./components/OrdersAndFillsPanel";
import { SignalToaster } from "./components/SignalToaster";
import { StreamLog } from "./components/StreamLog";
import { useBalance } from "./hooks/useBalance";
import { useFills } from "./hooks/useFills";
import { useIndices } from "./hooks/useIndices";
import { useMarketStocks } from "./hooks/useMarketStocks";
import { useOrders } from "./hooks/useOrders";
import { usePoll } from "./hooks/usePoll";
import { usePositions } from "./hooks/usePositions";
import { useStatus } from "./hooks/useStatus";
import { useStockNames } from "./hooks/useStockNames";
import { useStream } from "./hooks/useStream";
import { VIEWS, type ViewId } from "./lib/views";
import { StockDetail } from "./pages/StockDetail";
import { StrategyPage } from "./pages/Strategy";
import { WatchlistPage } from "./pages/WatchlistPage";

// 현재 화면은 URL 해시가 단일 진실 공급원 — 새로고침·뒤로가기·북마크가 그대로 동작한다
function subscribeHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function readView(): ViewId {
  const hash = window.location.hash.slice(1);
  return VIEWS.find((v) => v.id === hash)?.id ?? "desk";
}

export default function App() {
  const view = useSyncExternalStore(subscribeHash, readView);

  const { status, refetch: refetchStatus } = useStatus(3000);
  const { positions } = usePositions(5000);
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
    lastUpdated: marketUpdatedAt,
  } = useMarketStocks(30000);
  const { orders, error: ordError, refetch: refetchOrders } = useOrders(5000);
  const { fills, total: fillTotal, error: fillError } = useFills(10000);
  const { logs, connected } = useStream();
  const marketStatus = usePoll(api.getMarketStatus, 60_000);
  const risk = usePoll(api.getRiskMetrics, 10_000);

  // 내 종목(보유·주문·체결) — 차트 화면의 바로가기 목록이 된다
  const mySymbols = useMemo(
    () =>
      Array.from(
        new Set([
          ...positions.map((p) => p.symbol),
          ...orders.map((o) => o.symbol),
          ...fills.map((f) => f.symbol),
        ]),
      ),
    [positions, orders, fills],
  );
  // 종목 코드 대신 종목명을 보여주기 위한 심볼 → 이름 매핑 (전 화면 공유 캐시)
  const nameSymbols = useMemo(
    () => [...mySymbols, ...marketStocks.map((s) => s.symbol)],
    [mySymbols, marketStocks],
  );
  const stockNames = useStockNames(nameSymbols);

  return (
    <div className="flex h-dvh flex-col">
      <AppHeader
        view={view}
        status={status}
        markets={marketStatus?.markets ?? []}
        streamConnected={connected}
        onAction={refetchStatus}
      />
      <IndicesStrip indices={indices} error={indicesError} />
      <SignalToaster logs={logs} stockNames={stockNames} />

      <main className="min-h-0 flex-1 overflow-auto p-3">
        {view === "desk" && (
          // 좌: 내 돈(계좌·주문) / 우: 봇과 시장. xl(1280px) 이상에서는 한 화면에 고정되고
          // 각 패널이 안에서 스크롤된다. 그 아래에선 세로로 쌓여 페이지가 스크롤된다.
          <div className="grid grid-cols-1 gap-3 xl:h-full xl:min-h-[640px] xl:grid-cols-[minmax(0,1fr)_minmax(360px,30%)]">
            <div className="flex min-h-0 flex-col gap-3">
              <AccountSummary
                balance={balance}
                error={balanceError}
                lastUpdated={balanceUpdatedAt}
                buyingPower={risk?.buying_power}
                className="max-xl:max-h-[560px] xl:flex-[5]"
              />
              <OrdersAndFillsPanel
                orders={orders}
                fills={fills}
                ordersError={ordError}
                fillsError={fillError}
                fillsTotal={fillTotal}
                onRefetch={refetchOrders}
                stockNames={stockNames}
                className="max-xl:max-h-[420px] xl:flex-[2]"
              />
            </div>
            <div className="flex min-h-0 flex-col gap-3">
              <StreamLog
                logs={logs}
                connected={connected}
                stockNames={stockNames}
                dailyOrderCount={risk?.daily_order_count}
                className="max-xl:max-h-[360px] xl:flex-[2]"
              />
              <MarketStocksTable
                stocks={marketStocks}
                sortBy={marketSortBy}
                onSortChange={setMarketSortBy}
                error={marketError}
                isLoading={marketLoading}
                lastUpdated={marketUpdatedAt}
                stockNames={stockNames}
                className="max-xl:max-h-[480px] xl:flex-[3]"
              />
            </div>
          </div>
        )}

        {view === "chart" && (
          <StockDetail recentSymbols={mySymbols} stockNames={stockNames} />
        )}

        {view === "bot" && (
          <StrategyPage
            status={status}
            risk={risk}
            logs={logs}
            connected={connected}
            stockNames={stockNames}
          />
        )}

        {view === "watchlist" && <WatchlistPage />}
      </main>
    </div>
  );
}
