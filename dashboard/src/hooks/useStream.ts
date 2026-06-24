import { useEffect, useRef, useState } from "react";
import { createStreamSocket } from "../api/client";
import type { StreamMessage } from "../api/types";

const MAX_LOGS = 200;

export function useStream() {
  const [logs, setLogs] = useState<StreamMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = createStreamSocket((msg) => {
      const m = msg as StreamMessage;
      if (m.event_type === "heartbeat") return;
      setLogs((prev) => [m, ...prev].slice(0, MAX_LOGS));
    });

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // 3초 후 재연결 시도
      reconnectRef.current = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
    wsRef.current = ws;
  };

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { logs, connected };
}
