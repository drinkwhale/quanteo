import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { BotStatus } from "../api/types";

export function useStatus(intervalMs = 3000) {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .getStatus()
      .then(setStatus)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      );
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { status, error, refetch: refresh };
}
