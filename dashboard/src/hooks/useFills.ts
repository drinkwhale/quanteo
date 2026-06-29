import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { FillItem } from "../api/types";

export function useFills(intervalMs = 10000) {
  const [fills, setFills] = useState<FillItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .getFills(100)
      .then((res) => {
        setFills(res.items);
        setTotal(res.total);
      })
      .catch((e: unknown) => {
        // 브로커 없을 때(503)는 조용히 처리
        if (e instanceof Error && e.message.includes("503")) {
          setError(null);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      });
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { fills, total, error, refetch: refresh };
}
