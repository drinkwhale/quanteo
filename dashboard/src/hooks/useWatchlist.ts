import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { WatchlistResponse } from "../api/types";

/**
 * Stock Miner(screener)는 하루 한 번만 관심종목을 갱신하는 독립 서브시스템이라
 * 짧은 폴링이 무의미하다 — 기본 5분 간격 + 수동 새로고침 버튼으로 충분하다.
 */
export function useWatchlist(intervalMs = 300000) {
  const [watchlist, setWatchlist] = useState<WatchlistResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 아직 생성된 관심종목이 없는 정상 상태(404)는 에러가 아니라 빈 상태로 다룬다.
  const [notFound, setNotFound] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(() => {
    api
      .getWatchlist()
      .then((res) => {
        setWatchlist(res);
        setError(null);
        setNotFound(false);
      })
      .catch((e: unknown) => {
        const message = e instanceof Error ? e.message : String(e);
        if (message.startsWith("404")) {
          setWatchlist(null);
          setNotFound(true);
          setError(null);
        } else {
          setError(message);
        }
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { watchlist, error, notFound, isLoading, refetch: refresh };
}
