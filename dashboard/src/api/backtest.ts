// 백테스트 Control API 클라이언트

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export interface BacktestRunRequest {
  symbol: string;
  start_date?: string;
  end_date?: string;
  strategy_params?: Record<string, unknown>;
}

export interface BacktestRunResponse {
  run_id: string;
  status: string;
}

export interface BacktestStatusResponse {
  run_id: string;
  status: "running" | "completed" | "failed";
  created_at: string;
  completed_at?: string;
  error_msg?: string;
}

export interface BacktestMetrics {
  win_rate: number;
  profit_loss_ratio: number;
  mdd: number;
  sharpe_ratio: number;
  total_trades: number;
  annualized_return: number;
}

export interface BacktestResultResponse {
  run_id: string;
  status: "running" | "completed" | "failed";
  metrics?: BacktestMetrics;
  trades_count: number;
  equity_curve: number[];
  unfilled_signals_count: number;
}

export const backtestApi = {
  run: (req: BacktestRunRequest) =>
    request<BacktestRunResponse>("/backtest/run", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  status: (runId: string) =>
    request<BacktestStatusResponse>(`/backtest/status/${runId}`),

  results: (runId: string) =>
    request<BacktestResultResponse>(`/backtest/results/${runId}`),
};

export async function pollUntilDone(
  runId: string,
  onStatus: (s: BacktestStatusResponse) => void,
  intervalMs = 1500,
  timeoutMs = 120_000,
): Promise<BacktestResultResponse> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const s = await backtestApi.status(runId);
    onStatus(s);
    if (s.status === "completed" || s.status === "failed") {
      return backtestApi.results(runId);
    }
    await new Promise<void>((r) => setTimeout(r, intervalMs));
  }
  throw new Error("백테스트 타임아웃 (2분 초과)");
}
