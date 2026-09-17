import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { WatchlistResponse } from "../api/types";

/**
 * 관심종목은 사용자가 Telegram에서 "워치리스트 등록" 버튼을 눌러야만 갱신되는
 * 이벤트 기반 데이터라 짧은 폴링이 무의미하다 — 기본 5분 간격 + 수동 새로고침
 * 버튼으로 충분하다.
 */
export function useWatchlist(intervalMs = 300000) {
  const [watchlist, setWatchlist] = useState<WatchlistResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(() => {
    api
      .getWatchlist()
      .then((res) => {
        setWatchlist(res);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { watchlist, error, isLoading, refetch: refresh };
}
