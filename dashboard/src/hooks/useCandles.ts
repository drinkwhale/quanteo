import { useEffect, useState } from "react";
import { CandleItem, getCandles } from "../api/candles";

interface UseCandlesOptions {
  interval?: "1m" | "1d";
  count?: number;
  before?: string;
  adjusted?: boolean;
}

interface CandleResult {
  key: string;
  candles: CandleItem[];
  error: Error | null;
}

/**
 * 응답에 "어느 요청의 결과인지"(key)를 같이 들고 있다가, 현재 요청과 key가 다르면 버린다.
 * 종목을 빠르게 바꿨을 때 늦게 도착한 이전 종목 캔들이 새 종목 제목 아래 그려지는 것을 막는다.
 */
export function useCandles(
  symbol: string | null,
  options: UseCandlesOptions = {},
) {
  const { interval = "1d", count = 100, before, adjusted = true } = options;
  const key = symbol
    ? [symbol, interval, count, before ?? "", adjusted].join("|")
    : null;
  const [result, setResult] = useState<CandleResult | null>(null);

  useEffect(() => {
    if (!symbol || !key) return;
    let alive = true;

    getCandles(symbol, interval, count, before, adjusted)
      .then((response) => {
        if (alive) setResult({ key, candles: response.items, error: null });
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setResult({
          key,
          candles: [],
          error: err instanceof Error ? err : new Error("알 수 없는 오류"),
        });
      });

    return () => {
      alive = false;
    };
  }, [symbol, key, interval, count, before, adjusted]);

  const current = result?.key === key ? result : null;

  return {
    candles: current?.candles ?? [],
    isLoading: key !== null && current === null,
    error: current?.error ?? null,
  };
}
