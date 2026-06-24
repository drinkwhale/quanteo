import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { BotStatus } from "../api/types";

export function useStatus(intervalMs = 3000) {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(() => {
    api
      .getStatus()
      .then(setStatus)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      );
  }, []);

  useEffect(() => {
    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => clearInterval(id);
  }, [fetch, intervalMs]);

  return { status, error, refetch: fetch };
}
