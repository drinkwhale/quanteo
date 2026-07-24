import { useEffect, useState } from "react";

interface MarketStock {
  symbol: string;
  price: number;
  change_rate: number;
  trading_volume: number;
  trading_value: number;
  timestamp: string;
}

interface UseMarketStocksResult {
  stocks: MarketStock[];
  sortBy: "trading_value" | "volume" | "uptrend" | "downtrend";
  setSortBy: (
    sort: "trading_value" | "volume" | "uptrend" | "downtrend",
  ) => void;
  isLoading: boolean;
  error: string | null;
  lastUpdated: string | null;
}

export function useMarketStocks(
  pollInterval: number = 30000,
): UseMarketStocksResult {
  const [stocks, setStocks] = useState<MarketStock[]>([]);
  const [sortBy, setSortBy] = useState<
    "trading_value" | "volume" | "uptrend" | "downtrend"
  >("trading_value");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchMarketStocks = async (
    sort: "trading_value" | "volume" | "uptrend" | "downtrend",
  ) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/market-stocks?sort_by=${sort}&limit=10`,
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setStocks(data.data || []);
      setLastUpdated(data.timestamp);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "마켓 데이터 조회 실패";
      setError(message);
      setStocks([]);
    } finally {
      setIsLoading(false);
    }
  };

  // 초기 로드 및 정렬 변경 시
  useEffect(() => {
    fetchMarketStocks(sortBy);
  }, [sortBy]);

  // 주기적 갱신
  useEffect(() => {
    const timer = setInterval(() => {
      fetchMarketStocks(sortBy);
    }, pollInterval);

    return () => clearInterval(timer);
  }, [sortBy, pollInterval]);

  return {
    stocks,
    sortBy,
    setSortBy,
    isLoading,
    error,
    lastUpdated,
  };
}
