import { useState } from "react";
import { fmtPrice } from "../lib/format";
import { TIMESTAMP_CELL_CLASS } from "../lib/utils";

interface MarketStock {
  symbol: string;
  price: number;
  change_rate: number;
  trading_volume: number;
  trading_value: number;
  timestamp: string;
}

interface Props {
  stocks: MarketStock[];
  error?: string | null;
  isLoading?: boolean;
}

export function MarketStocksTable({ stocks, error, isLoading }: Props) {
  return (
    <>
      {error && (
        <p className="px-4 py-2 text-negative text-xs font-sans border-b border-border bg-negative/5">
          {error}
        </p>
      )}

      {isLoading && (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          데이터 로딩 중...
        </p>
      )}

      {!isLoading && stocks.length === 0 ? (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          종목 데이터가 없습니다
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="px-4 py-2 text-left">종목</th>
                <th className="px-4 py-2 text-right">현재가</th>
                <th className="px-4 py-2 text-right">등락률</th>
                <th className="px-4 py-2 text-right">거래대금</th>
                <th className="px-4 py-2 text-right">거래량</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((stock) => (
                <tr
                  key={stock.symbol}
                  className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                >
                  <td className="px-4 py-2 font-medium">{stock.symbol}</td>
                  <td className="px-4 py-2 text-right text-white tabular-nums">
                    {fmtPrice(stock.price, "domestic")}
                  </td>
                  <td
                    className={`px-4 py-2 text-right font-semibold tabular-nums ${
                      stock.change_rate > 0
                        ? "text-positive"
                        : stock.change_rate < 0
                          ? "text-negative"
                          : "text-muted"
                    }`}
                  >
                    {stock.change_rate > 0 ? "+" : ""}
                    {stock.change_rate.toFixed(2)}%
                  </td>
                  <td className="px-4 py-2 text-right text-white tabular-nums">
                    {(stock.trading_value / 100000000).toFixed(1)}억
                  </td>
                  <td className="px-4 py-2 text-right text-muted tabular-nums text-xs">
                    {(stock.trading_volume / 1000000).toFixed(1)}M
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
