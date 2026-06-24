import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { PositionItem } from "../api/types";

export function usePositions(intervalMs = 5000) {
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
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
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { positions, total, error, refetch: refresh };
}
