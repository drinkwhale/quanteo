import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { BalanceInfo } from "../api/types";

export function useBalance(intervalMs = 2000) {
  const [balance, setBalance] = useState<BalanceInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(() => {
    api
      .getBalance()
      .then((res) => {
        setBalance(res);
        setError(null);
        setLastUpdated(new Date());
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

  return { balance, error, lastUpdated, refetch: refresh };
}
