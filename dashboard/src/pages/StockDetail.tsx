import { useState, useMemo } from "react";
import { Panel } from "../components/Panel";
import { IntervalToggle } from "../components/chart/IntervalToggle";
import { PriceChart } from "../components/chart/PriceChart";
import { SymbolQuickPick } from "../components/chart/SymbolQuickPick";
import { useCandles } from "../hooks/useCandles";
import { useStockNames } from "../hooks/useStockNames";

interface StockDetailProps {
  recentSymbols?: string[];
}

export function StockDetail({ recentSymbols }: StockDetailProps) {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [interval, setInterval] = useState<"1m" | "1d">("1d");

  const { candles, isLoading, error } = useCandles(selectedSymbol, {
    interval,
  });

  const stockNames = useStockNames(selectedSymbol ? [selectedSymbol] : []);
  const displayName = useMemo(() => {
    if (!selectedSymbol) return null;
    return stockNames.get(selectedSymbol) || selectedSymbol;
  }, [selectedSymbol, stockNames]);

  return (
    <Panel title={`종목상세${displayName ? ` - ${displayName}` : ""}`}>
      <div className="space-y-4">
        <SymbolQuickPick
          onSymbolSelect={setSelectedSymbol}
          recentSymbols={recentSymbols}
        />

        {selectedSymbol && (
          <>
            <div className="flex justify-between items-center">
              <h3 className="text-sm font-semibold">캔들 차트</h3>
              <IntervalToggle value={interval} onChange={setInterval} />
            </div>

            <PriceChart candles={candles} isLoading={isLoading} error={error} />
          </>
        )}

        {!selectedSymbol && (
          <div className="text-center py-12 text-muted">
            종목을 선택하여 차트를 보세요.
          </div>
        )}
      </div>
    </Panel>
  );
}
