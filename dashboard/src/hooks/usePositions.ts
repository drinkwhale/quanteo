import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { PositionItem } from "../api/types";

export function usePositions(intervalMs = 5000) {
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(() => {
    api
      .getPositions()
      .then((res) => {
        setPositions(res.items);
        setTotal(res.total);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      );
  }, []);

  useEffect(() => {
    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => clearInterval(id);
  }, [fetch, intervalMs]);

  return { positions, total, error, refetch: fetch };
}
