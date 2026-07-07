import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { IndexQuoteItem } from "../api/types";

/** 30초 간격 폴링 — 백엔드도 30초 캐시라 이보다 짧게 당겨도 실효 없음. */
export function useIndices(intervalMs = 30000) {
  const [indices, setIndices] = useState<IndexQuoteItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .getIndices()
      .then((res) => {
        setIndices(res.items);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      );
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { indices, error };
}
