import { useState } from "react";
import { Panel } from "../components/Panel";
import { Segmented } from "../components/Segmented";
import { PriceChart } from "../components/chart/PriceChart";
import { SymbolQuickPick } from "../components/chart/SymbolQuickPick";
import { useCandles } from "../hooks/useCandles";
import { useStockNames } from "../hooks/useStockNames";

const INTERVAL_OPTIONS = [
  { value: "1m", label: "1분봉" },
  { value: "1d", label: "일봉" },
] as const;

interface StockDetailProps {
  /** 보유·최근 거래 종목 (App이 포지션·주문·체결에서 모은 목록) */
  recentSymbols: string[];
  stockNames: Map<string, string>;
}

export function StockDetail({ recentSymbols, stockNames }: StockDetailProps) {
  const [picked, setPicked] = useState<string | null>(null);
  const [interval, setInterval] = useState<"1m" | "1d">("1d");

  // 직접 고르기 전에는 첫 보유 종목을 띄워, 화면에 들어오자마자 차트가 보이게 한다.
  // 포지션·주문·체결 폴링이 따로 도착하며 목록 순서가 바뀌어도 차트가 저절로
  // 다른 종목으로 넘어가지 않도록, 자동 선택은 처음 한 번만 한다.
  const [autoPicked, setAutoPicked] = useState<string | null>(null);
  if (autoPicked === null && recentSymbols.length > 0) {
    setAutoPicked(recentSymbols[0]);
  }
  const selected = picked ?? autoPicked;

  const { candles, isLoading, error } = useCandles(selected, { interval });

  // 코드로 직접 조회한 종목은 App의 이름 캐시에 없을 수 있어 따로 조회한다
  const pickedNames = useStockNames(picked ? [picked] : []);
  const displayName = selected
    ? (stockNames.get(selected) ?? pickedNames.get(selected) ?? selected)
    : null;

  return (
    <div className="grid grid-cols-1 gap-3 lg:h-full lg:grid-cols-[260px_minmax(0,1fr)]">
      <Panel title="종목" meta={`${recentSymbols.length}개`}>
        <SymbolQuickPick
          symbols={recentSymbols}
          names={stockNames}
          selected={selected}
          onSymbolSelect={setPicked}
        />
      </Panel>

      <Panel
        title={displayName ?? "차트"}
        meta={displayName && displayName !== selected ? selected : undefined}
        className="min-h-[420px]"
        bodyClassName="overflow-hidden p-2"
        actions={
          <Segmented
            label="봉 주기"
            options={INTERVAL_OPTIONS}
            value={interval}
            onChange={setInterval}
          />
        }
      >
        {selected ? (
          <PriceChart candles={candles} isLoading={isLoading} error={error} />
        ) : (
          <p className="state-msg">
            왼쪽에서 종목을 고르거나 6자리 종목코드로 조회하면 캔들 차트가
            표시됩니다.
          </p>
        )}
      </Panel>
    </div>
  );
}
