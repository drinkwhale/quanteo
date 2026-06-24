import { useEffect, useRef, useState } from "react";
import { createStreamSocket } from "../api/client";
import type { StreamMessage } from "../api/types";

const MAX_LOGS = 200;

export type LogEntry = StreamMessage & { _key: number };

export function useStream() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(false);
  const keyRef = useRef(0);

  const connect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = createStreamSocket((msg) => {
      const m = msg as StreamMessage;
      if (m.event_type === "heartbeat") return;
      setLogs((prev) =>
        [{ ...m, _key: keyRef.current++ }, ...prev].slice(0, MAX_LOGS),
      );
    });

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // 마운트 상태일 때만 재연결 — 언마운트 후 ws.close()가 onclose를 트리거하는 것 방지
      if (mountedRef.current) {
        reconnectRef.current = setTimeout(connect, 3000);
      }
    };
    ws.onerror = () => ws.close();
    wsRef.current = ws;
  };

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { logs, connected };
}
