import { useEffect, useState } from "react";
import { CandleItem, getCandles } from "../api/candles";

interface UseCandlesOptions {
  interval?: "1m" | "1d";
  count?: number;
  before?: string;
  adjusted?: boolean;
}

export function useCandles(
  symbol: string | null,
  options: UseCandlesOptions = {},
) {
  const [candles, setCandles] = useState<CandleItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!symbol) {
      setCandles([]);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    getCandles(
      symbol,
      options.interval ?? "1d",
      options.count ?? 100,
      options.before,
      options.adjusted ?? true,
    )
      .then((response) => setCandles(response.items))
      .catch((err) =>
        setError(err instanceof Error ? err : new Error("알 수 없는 오류")),
      )
      .finally(() => setIsLoading(false));
  }, [
    symbol,
    options.interval,
    options.count,
    options.before,
    options.adjusted,
  ]);

  return { candles, isLoading, error };
}
