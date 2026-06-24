import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { OrderItem } from "../api/types";

export function useOrders(intervalMs = 5000) {
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(() => {
    api
      .getOrders(100)
      .then((res) => {
        setOrders(res.items);
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

  return { orders, total, error, refetch: fetch };
}
