/**
 * 전략 모니터링 페이지
 *
 * - CCI 현황 패널 (4개 타임프레임)
 * - 신뢰도 스코어 게이지 (0~8점)
 * - 실시간 시그널 토스트 (WebSocket)
 * - 포지션 진행 바
 * - 백테스트 실행 UI
 * - 킬스위치
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  type BacktestMetrics,
  type BacktestStatusResponse,
  backtestApi,
  pollUntilDone,
} from "../api/backtest";
import { KillSwitchButton } from "../components/KillSwitchButton";
import { Panel } from "../components/Panel";
import type { PositionItem } from "../api/types";
import type { LogEntry } from "../hooks/useStream";

// ============================================================================
// 타입
// ============================================================================

interface CciTimeframe {
  label: string;
  value: number | null;
  signal: "buy" | "sell" | "neutral";
  cross: "golden" | "dead" | null;
}

interface SignalToast {
  id: number;
  side: "BUY" | "SELL";
  symbol: string;
  price: number;
  reason: string;
  ts: string;
}

// ============================================================================
// 서브 컴포넌트: CCI 패널
// ============================================================================

function CciPanel({ timeframes }: { timeframes: CciTimeframe[] }) {
  return (
    <Panel title="CCI 현황">
      <div className="p-4 space-y-3">
        <div className="grid grid-cols-2">
          {timeframes.map((tf, i) => {
            const isLastRow =
              i >= timeframes.length - (timeframes.length % 2 || 2);
            return (
              <div
                key={tf.label}
                className={`py-2 space-y-1 ${i % 2 === 0 ? "pr-3" : "pl-3"} ${
                  isLastRow ? "" : "border-b border-border"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-muted">
                    {tf.label}
                  </span>
                  {tf.cross === "golden" && (
                    <span className="text-[10px] font-mono text-positive">
                      GC
                    </span>
                  )}
                  {tf.cross === "dead" && (
                    <span className="text-[10px] font-mono text-negative">
                      DC
                    </span>
                  )}
                </div>
                <div
                  className={`text-sm font-mono font-bold ${
                    tf.signal === "buy"
                      ? "text-positive"
                      : tf.signal === "sell"
                        ? "text-negative"
                        : "text-muted"
                  }`}
                >
                  {tf.value !== null ? tf.value.toFixed(1) : "—"}
                </div>
                <div className="text-[10px] font-mono text-muted capitalize">
                  {tf.signal}
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-muted font-mono">
          * 실시간 데이터는 /strategy/status 엔드포인트 연동 후 활성화
        </p>
      </div>
    </Panel>
  );
}

// ============================================================================
// 서브 컴포넌트: 신뢰도 스코어 게이지
// ============================================================================

interface ReliabilityProps {
  score: number | null;
  breakdown: Record<string, boolean>;
}

const RELIABILITY_STATUS = [
  {
    min: 7,
    label: "적극매수",
    color: "text-positive",
    bar: "bg-positive",
    badge: "bg-positive/10 border-positive/40 text-positive",
  },
  {
    min: 4,
    label: "소극매수",
    color: "text-warning",
    bar: "bg-warning",
    badge: "bg-warning/10 border-warning/40 text-warning",
  },
  {
    min: 0,
    label: "관망",
    color: "text-muted",
    bar: "bg-border",
    badge: "bg-muted/10 border-border text-muted",
  },
  {
    min: -Infinity,
    label: "매도검토",
    color: "text-negative",
    bar: "bg-negative",
    badge: "bg-negative/10 border-negative/40 text-negative",
  },
] as const;

function reliabilityStatus(score: number | null) {
  if (score === null) return null;
  return (
    RELIABILITY_STATUS.find((s) => score >= s.min) ??
    RELIABILITY_STATUS[RELIABILITY_STATUS.length - 1]
  );
}

function ReliabilityGauge({ score, breakdown }: ReliabilityProps) {
  const status = reliabilityStatus(score);
  const color = status?.color ?? "text-muted";
  const barColor = status?.bar ?? "bg-border";

  const pct =
    score !== null ? Math.max(0, Math.min(100, (score / 8) * 100)) : 0;

  return (
    <Panel title="신뢰도 스코어">
      <div className="p-4 space-y-3">
        <div className="flex items-end gap-2 flex-wrap">
          <span className={`text-3xl font-mono font-bold ${color}`}>
            {score !== null ? score : "—"}
          </span>
          <span className="text-muted font-mono text-sm mb-1">/ 8</span>
          {status && (
            <span
              className={`ml-auto text-[10px] font-mono font-semibold px-2 py-1 rounded border ${status.badge}`}
            >
              {status.label}
            </span>
          )}
        </div>

        <div
          role="progressbar"
          aria-valuenow={score ?? 0}
          aria-valuemin={0}
          aria-valuemax={8}
          aria-label="신뢰도 스코어"
          className="w-full h-2 bg-surface rounded-full overflow-hidden"
        >
          <div
            className={`h-full rounded-full transition-all ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>

        {Object.keys(breakdown).length > 0 && (
          <ul className="space-y-1">
            {Object.entries(breakdown).map(([key, passed]) => (
              <li
                key={key}
                className="flex items-center gap-2 text-xs font-mono"
              >
                <span
                  aria-hidden="true"
                  className={passed ? "text-positive" : "text-muted"}
                >
                  {passed ? "✓" : "○"}
                </span>
                <span className="sr-only">{passed ? "통과" : "미통과"}</span>
                <span className={passed ? "text-white" : "text-muted"}>
                  {key}
                </span>
              </li>
            ))}
          </ul>
        )}
        {Object.keys(breakdown).length === 0 && (
          <p className="text-[10px] text-muted font-mono">
            * 스코어 데이터 대기 중
          </p>
        )}
      </div>
    </Panel>
  );
}

// ============================================================================
// 서브 컴포넌트: 포지션 진행 바
// ============================================================================

function PositionProgressBars({ positions }: { positions: PositionItem[] }) {
  // 분할 매수 스텝: 1차 30%, 2차 50%, 3차 20% (스펙 기준 예시)
  const STEPS = [
    { label: "1차", pct: 30 },
    { label: "2차", pct: 50 },
    { label: "3차", pct: 20 },
  ];

  if (positions.length === 0) {
    return (
      <Panel title="포지션 현황">
        <p className="p-4 text-xs text-muted font-mono">보유 포지션 없음</p>
      </Panel>
    );
  }

  return (
    <Panel title="포지션 현황">
      <div className="p-4 space-y-3">
        {positions.slice(0, 5).map((pos) => (
          <div key={pos.symbol} className="space-y-1">
            <div className="flex justify-between text-xs font-mono">
              <span className="text-white">{pos.symbol}</span>
              <span className="text-muted">{pos.qty.toLocaleString()}주</span>
            </div>
            <div className="flex gap-0.5 h-2">
              {STEPS.map((step, i) => (
                <div
                  key={step.label}
                  className="h-full rounded-sm"
                  style={{
                    width: `${step.pct}%`,
                    backgroundColor:
                      i === 0
                        ? "rgb(34 197 94 / 0.8)"
                        : i === 1
                          ? "rgb(34 197 94 / 0.5)"
                          : "rgb(34 197 94 / 0.25)",
                  }}
                  title={`${step.label} ${step.pct}%`}
                />
              ))}
            </div>
            <div className="flex gap-2 text-[10px] font-mono text-muted">
              {STEPS.map((s) => (
                <span key={s.label}>
                  {s.label} {s.pct}%
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ============================================================================
// 서브 컴포넌트: 백테스트 UI
// ============================================================================

function BacktestPanel() {
  const [symbol, setSymbol] = useState("005930");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [running, setRunning] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 언마운트 시 진행 중인 폴링 취소
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function run() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setRunning(true);
    setStatusMsg("백테스트 시작...");
    setResult(null);
    setError(null);

    try {
      const { run_id } = await backtestApi.run({
        symbol,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });

      const res = await pollUntilDone(
        run_id,
        (s: BacktestStatusResponse) => {
          setStatusMsg(`실행 중... (${s.status})`);
        },
        1500,
        120_000,
        controller.signal,
      );

      if (res.status === "failed") {
        setError("백테스트 실패");
      } else if (res.metrics) {
        setResult(res.metrics);
        setStatusMsg("완료");
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.message.includes("취소")) return;
      setError(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Panel title="백테스트">
      <div className="p-4 space-y-4">
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-muted">종목코드</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-surface border border-border rounded px-2 py-1 text-xs font-mono text-white focus:border-accent"
              placeholder="005930"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-muted">시작일</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-surface border border-border rounded px-2 py-1 text-xs font-mono text-white focus:border-accent"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-muted">종료일</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-surface border border-border rounded px-2 py-1 text-xs font-mono text-white focus:border-accent"
            />
          </div>
        </div>

        <button
          type="button"
          onClick={run}
          disabled={running || !symbol}
          className="w-full py-2 rounded bg-accent/10 text-accent border border-accent/30 text-sm font-mono font-semibold
                   hover:bg-accent/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {running ? (statusMsg ?? "실행 중...") : "백테스트 실행"}
        </button>

        {error && (
          <p className="text-xs font-mono text-negative bg-negative/5 border border-negative/20 rounded px-3 py-2">
            {error}
          </p>
        )}

        {result && (
          <dl className="text-xs font-mono">
            {(
              [
                {
                  label: "승률 %",
                  value: `${(result.win_rate * 100).toFixed(1)}%`,
                  tone: "neutral",
                },
                {
                  label: "MDD %",
                  value: `${(result.mdd * 100).toFixed(1)}%`,
                  tone: "negative",
                },
                {
                  label: "샤프 지수",
                  value: result.sharpe_ratio.toFixed(2),
                  tone: result.sharpe_ratio >= 0 ? "positive" : "negative",
                },
                {
                  label: "연환산 수익률 %",
                  value: `${(result.annualized_return * 100).toFixed(1)}%`,
                  tone: result.annualized_return >= 0 ? "positive" : "negative",
                },
                {
                  label: "손익비",
                  value: result.profit_loss_ratio.toFixed(2),
                  tone: "neutral",
                },
                {
                  label: "총 거래수",
                  value: String(result.total_trades),
                  tone: "neutral",
                },
              ] as {
                label: string;
                value: string;
                tone: "positive" | "negative" | "neutral";
              }[]
            ).map(({ label, value, tone }, i, arr) => (
              <div
                key={label}
                className={`flex items-center justify-between py-1.5 ${
                  i === arr.length - 1 ? "" : "border-b border-border"
                }`}
              >
                <dt className="text-muted">{label}</dt>
                <dd
                  className={`font-bold ${
                    tone === "positive"
                      ? "text-positive"
                      : tone === "negative"
                        ? "text-negative"
                        : "text-white"
                  }`}
                >
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </Panel>
  );
}

// ============================================================================
// 서브 컴포넌트: 시그널 토스트
// ============================================================================

function SignalToasts({ toasts }: { toasts: SignalToast[] }) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[var(--z-toast)] flex flex-col gap-2 max-w-xs">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex flex-col gap-1 px-4 py-3 rounded-lg border text-xs font-mono
                      animate-[fadeIn_0.2s_ease-out] motion-reduce:animate-none motion-reduce:opacity-100 ${
                        t.side === "BUY"
                          ? "bg-positive/10 border-positive/60 text-positive"
                          : "bg-negative/10 border-negative/60 text-negative"
                      }`}
        >
          <div className="font-bold text-sm">
            {t.side === "BUY" ? "▲ 매수 시그널" : "▼ 매도 시그널"}
          </div>
          <div className="text-white">
            {t.symbol} @ {t.price.toLocaleString()}
          </div>
          <div className="text-muted truncate">{t.reason}</div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// 메인 Strategy 페이지
// ============================================================================

interface Props {
  logs: LogEntry[];
  positions: PositionItem[];
  onKill: () => void;
}

const PLACEHOLDER_CCI: CciTimeframe[] = [
  { label: "5m", value: null, signal: "neutral", cross: null },
  { label: "15m", value: null, signal: "neutral", cross: null },
  { label: "1h", value: null, signal: "neutral", cross: null },
  { label: "1d", value: null, signal: "neutral", cross: null },
];

const TOAST_TTL = 8_000;

export function StrategyPage({ logs, positions, onKill }: Props) {
  const [toasts, setToasts] = useState<SignalToast[]>([]);
  const toastKeyRef = useRef(0);
  const seenRef = useRef(new Set<string>());

  // 스트림 로그에서 signal 이벤트를 토스트로 변환
  useEffect(() => {
    const latest = logs[0];
    if (!latest) return;
    if (latest.event_type !== "signal") return;

    const dedupeKey = `${latest._key}`;
    if (seenRef.current.has(dedupeKey)) return;
    seenRef.current.add(dedupeKey);

    // M3: as 캐스트 대신 런타임 타입 검증
    const rawPayload = latest.payload as Record<string, unknown> | null;
    if (!rawPayload) return;

    const side = rawPayload.side;
    const symbol = rawPayload.symbol;
    if (typeof side !== "string" || typeof symbol !== "string") return;
    if (side !== "BUY" && side !== "SELL") return;

    const toast: SignalToast = {
      id: toastKeyRef.current++,
      side,
      symbol,
      price: typeof rawPayload.price === "number" ? rawPayload.price : 0,
      reason: typeof rawPayload.reason === "string" ? rawPayload.reason : "",
      ts: latest.timestamp,
    };

    setToasts((prev) => [toast, ...prev].slice(0, 5));

    // H6: setTimeout id를 반환해서 언마운트 시 정리
    const timerId = setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== toast.id)),
      TOAST_TTL,
    );
    return () => clearTimeout(timerId);
  }, [logs]);

  // CCI 스냅샷: 스트림에서 cci_snapshot 이벤트 파싱
  const cciData = useCallback((): CciTimeframe[] => {
    const snap = logs.find((l) => l.event_type === "cci_snapshot");
    if (!snap) return PLACEHOLDER_CCI;

    const p = snap.payload as Record<string, unknown> | null;
    if (!p) return PLACEHOLDER_CCI;

    return (["5m", "15m", "1h", "1d"] as const).map((tf) => {
      const data = p[tf] as
        { value: number; signal: string; cross: string | null } | undefined;
      return {
        label: tf,
        value: data?.value ?? null,
        signal: (data?.signal as CciTimeframe["signal"]) ?? "neutral",
        cross: (data?.cross as CciTimeframe["cross"]) ?? null,
      };
    });
  }, [logs]);

  // 신뢰도 스코어: 스트림에서 reliability_score 이벤트 파싱
  const reliabilityData = useCallback((): {
    score: number | null;
    breakdown: Record<string, boolean>;
  } => {
    const snap = logs.find((l) => l.event_type === "reliability_score");
    if (!snap) return { score: null, breakdown: {} };

    const p = snap.payload as {
      score: number;
      breakdown: Record<string, boolean>;
    } | null;
    if (!p) return { score: null, breakdown: {} };
    return { score: p.score, breakdown: p.breakdown };
  }, [logs]);

  const { score, breakdown } = reliabilityData();
  const cciFrames = cciData();

  return (
    <>
      <SignalToasts toasts={toasts} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* 왼쪽: CCI + 포지션 */}
        <div className="space-y-4">
          <CciPanel timeframes={cciFrames} />
          <PositionProgressBars positions={positions} />
        </div>

        {/* 가운데: 신뢰도 + 백테스트 */}
        <div className="space-y-4">
          <ReliabilityGauge score={score} breakdown={breakdown} />
          <BacktestPanel />
        </div>

        {/* 오른쪽: 킬스위치 + 최근 시그널 */}
        <div className="space-y-4">
          <Panel title="긴급 제어">
            <div className="p-4">
              <KillSwitchButton onSuccess={onKill} fullWidth />
            </div>
          </Panel>

          <Panel title="최근 시그널">
            <div className="p-4 space-y-2">
              {logs.filter((l) => l.event_type === "signal").length === 0 ? (
                <p className="text-xs text-muted font-mono">대기 중...</p>
              ) : (
                logs
                  .filter((l) => l.event_type === "signal")
                  .slice(0, 8)
                  .map((l) => {
                    const p = l.payload as {
                      side?: string;
                      symbol?: string;
                      price?: number;
                    } | null;
                    return (
                      <div
                        key={l._key}
                        className={`flex items-center justify-between text-xs font-mono px-2 py-1 rounded ${
                          p?.side === "BUY"
                            ? "text-positive bg-positive/5"
                            : "text-negative bg-negative/5"
                        }`}
                      >
                        <span>
                          {p?.side === "BUY" ? "▲" : "▼"} {p?.symbol}
                        </span>
                        <span>{p?.price?.toLocaleString()}</span>
                      </div>
                    );
                  })
              )}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
