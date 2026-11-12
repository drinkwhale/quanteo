import type { MarketSort, MarketStock } from "../hooks/useMarketStocks";
import {
  fmtPrice,
  fmtStamp,
  marketOf,
  stockLabel,
  trendClass,
} from "../lib/format";
import { cn } from "../lib/utils";
import { Panel } from "./Panel";
import { Segmented } from "./Segmented";

const SORT_OPTIONS = [
  { value: "trading_value", label: "거래대금" },
  { value: "volume", label: "거래량" },
  { value: "uptrend", label: "급상승" },
  { value: "downtrend", label: "급하락" },
] as const;

const EOK = 100_000_000;
const MAN = 10_000;

interface Props {
  stocks: MarketStock[];
  sortBy: MarketSort;
  onSortChange: (sort: MarketSort) => void;
  error?: string | null;
  isLoading?: boolean;
  /** 스크리너 스냅샷 기준 시각 — 실시간이 아니라 수집 시점 데이터라 항상 같이 보여준다 */
  lastUpdated?: string | null;
  stockNames: Map<string, string>;
  className?: string;
}

/** 시장 주도주 — 봇이 매매하는 시장이 지금 어디로 쏠려 있는지 보는 참고 패널. */
export function MarketStocksTable({
  stocks,
  sortBy,
  onSortChange,
  error,
  isLoading,
  lastUpdated,
  stockNames,
  className,
}: Props) {
  const isVolume = sortBy === "volume";

  return (
    <Panel
      title="시장 주도주"
      meta={lastUpdated ? `${fmtStamp(lastUpdated)} 수집` : undefined}
      className={className}
      actions={
        <Segmented
          label="주도주 정렬 기준"
          options={SORT_OPTIONS}
          value={sortBy}
          onChange={onSortChange}
        />
      }
    >
      {error && <p className="state-err">주도주 조회 실패 — {error}</p>}

      {stocks.length === 0 ? (
        // 폴링마다 isLoading이 켜지므로, 이미 표가 있으면 로딩 문구로 덮지 않는다(깜빡임 방지)
        <p className="state-msg">
          {isLoading
            ? "주도주 불러오는 중…"
            : "수집된 시장 데이터가 없습니다. 스크리너가 한 번 돌면 채워집니다."}
        </p>
      ) : (
        <table className="tbl">
          <thead>
            <tr>
              <th scope="col" className="w-8">
                <span className="sr-only">순위</span>
              </th>
              <th scope="col">종목</th>
              <th scope="col" className="r">
                현재가
              </th>
              <th scope="col" className="r">
                등락률
              </th>
              <th scope="col" className="r">
                {isVolume ? "거래량" : "거래대금"}
              </th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock, i) => (
              <tr key={stock.symbol}>
                <td className="text-xs text-muted">{i + 1}</td>
                <td className="font-semibold text-ink">
                  {stockLabel(stock.symbol, stockNames)}
                </td>
                <td className="r text-ink">
                  {fmtPrice(stock.price, marketOf(stock.symbol))}
                </td>
                <td
                  className={cn(
                    "r font-semibold",
                    trendClass(stock.change_rate),
                  )}
                >
                  {stock.change_rate > 0 ? "+" : ""}
                  {stock.change_rate.toFixed(2)}%
                </td>
                <td className="r text-dim">
                  {isVolume
                    ? `${(stock.trading_volume / MAN).toLocaleString("ko-KR", { maximumFractionDigits: 0 })}만`
                    : `${(stock.trading_value / EOK).toLocaleString("ko-KR", { maximumFractionDigits: 0 })}억`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
