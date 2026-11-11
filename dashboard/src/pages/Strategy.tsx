/**
 * 전략·봇 화면 — "봇이 지금 어떤 규칙으로, 어떤 판단을 하고 있나"를 본다.
 *
 * - 운용 상태: 단계적 킬스위치(halt level) 사다리 + 운용 조건
 * - 전략 신호: CCI 멀티 타임프레임, 신뢰도 스코어, 최근 시그널
 * - 봇 활동: 실시간 이벤트 로그
 * - 백테스트 실행
 *
 * 봇 제어 버튼은 여기 두지 않는다 — 헤더(BotControls) 한 곳에만 있다.
 */

import { Check, Minus } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import {
  type BacktestMetrics,
  type BacktestStatusResponse,
  backtestApi,
  pollUntilDone,
} from "../api/backtest";
import type { BotStatus, RiskMetrics } from "../api/types";
import { Panel } from "../components/Panel";
import { StreamLog } from "../components/StreamLog";
import type { LogEntry } from "../hooks/useStream";
import {
  fmtClock,
  fmtPrice,
  fmtStamp,
  fmtUptime,
  SIDE_LABEL,
  stockLabel,
  trendClass,
} from "../lib/format";
import { HALT_META, HALT_ORDER, TONE_CLASS } from "../lib/halt";
import { cn } from "../lib/utils";

// ============================================================================
// 운용 상태
// ============================================================================

function Fact({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="num text-right text-data text-ink">{children}</dd>
    </div>
  );
}

function BotStatePanel({
  status,
  risk,
}: {
  status: BotStatus | null;
  risk: RiskMetrics | null;
}) {
  return (
    <Panel title="운용 상태">
      <ol className="p-2">
        {HALT_ORDER.map((level) => {
          const meta = HALT_META[level];
          const isCurrent = status?.halt_level === level;
          return (
            <li
              key={level}
              aria-current={isCurrent ? "step" : undefined}
              className={cn(
                "flex gap-3 rounded-md border px-3 py-2.5",
                isCurrent
                  ? TONE_CLASS[meta.tone].pill
                  : "border-transparent text-muted",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                  isCurrent
                    ? TONE_CLASS[meta.tone].dot
                    : "border border-line-strong",
                )}
              />
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-data font-semibold">
                  {meta.label}
                  {isCurrent && (
                    <span className="text-2xs font-medium opacity-80">
                      현재 단계
                    </span>
                  )}
                </div>
                <p
                  className={cn(
                    "mt-0.5 text-xs leading-relaxed",
                    isCurrent ? "text-ink" : "text-muted",
                  )}
                >
                  {meta.desc}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      <dl className="divide-y divide-line/60 border-t border-line px-4 py-1">
        <Fact label="환경">
          {status ? (
            <span
              className={
                status.env === "prod" ? "font-semibold text-danger" : ""
              }
            >
              {status.env === "prod" ? "실전투자" : "모의투자"}
            </span>
          ) : (
            "—"
          )}
        </Fact>
        <Fact label="시장">
          {status ? (status.market === "domestic" ? "국내" : "해외") : "—"}
        </Fact>
        <Fact label="가동 시간">
          {status ? fmtUptime(status.uptime_seconds) : "—"}
        </Fact>
        <Fact label="시작 시각">
          {status?.started_at ? fmtStamp(status.started_at) : "—"}
        </Fact>
        <Fact label="오늘 주문">
          {risk ? `${risk.daily_order_count}건` : "—"}
        </Fact>
        <Fact label="주문가능금액">
          {risk?.buying_power != null
            ? fmtPrice(risk.buying_power, "domestic")
            : "—"}
        </Fact>
      </dl>

      <p className="border-t border-line px-4 py-3 text-xs leading-relaxed text-muted">
        리스크 한도와 전략 파라미터는 설정 파일(quanteo.yaml)에서 관리합니다. 이
        화면에서는 현재 적용 상태만 확인할 수 있습니다.
      </p>
    </Panel>
  );
}

// ============================================================================
// 전략 신호 — CCI 멀티 타임프레임 + 신뢰도 스코어 + 최근 시그널
// ============================================================================

interface CciTimeframe {
  key: string;
  label: string;
  value: number | null;
  signal: "buy" | "sell" | "neutral";
  cross: "golden" | "dead" | null;
}

const CCI_FRAMES = [
  { key: "5m", label: "5분" },
  { key: "15m", label: "15분" },
  { key: "1h", label: "1시간" },
  { key: "1d", label: "일봉" },
] as const;

const CCI_SIGNAL: Record<
  CciTimeframe["signal"],
  { label: string; cls: string }
> = {
  buy: { label: "매수", cls: "text-up" },
  sell: { label: "매도", cls: "text-down" },
  neutral: { label: "중립", cls: "text-muted" },
};

function parseCci(logs: LogEntry[]): CciTimeframe[] | null {
  const snap = logs.find((l) => l.event_type === "cci_snapshot");
  const p = snap?.payload as Record<string, unknown> | null | undefined;
  if (!p) return null;

  return CCI_FRAMES.map(({ key, label }) => {
    const data = p[key] as
      { value: number; signal: string; cross: string | null } | undefined;
    return {
      key,
      label,
      value: data?.value ?? null,
      signal: (data?.signal as CciTimeframe["signal"]) ?? "neutral",
      cross: (data?.cross as CciTimeframe["cross"]) ?? null,
    };
  });
}

const RELIABILITY_MAX = 8;

/** 점수 구간 → 판정. 매수 쪽은 시세 축 up, 매도 쪽은 down. */
function reliabilityVerdict(score: number): { label: string; cls: string } {
  if (score >= 7) return { label: "적극매수", cls: "text-up" };
  if (score >= 4) return { label: "소극매수", cls: "text-up" };
  if (score >= 0) return { label: "관망", cls: "text-dim" };
  return { label: "매도검토", cls: "text-down" };
}

function parseReliability(
  logs: LogEntry[],
): { score: number; breakdown: Record<string, boolean> } | null {
  const snap = logs.find((l) => l.event_type === "reliability_score");
  const p = snap?.payload as {
    score: number;
    breakdown: Record<string, boolean>;
  } | null;
  return p ? { score: p.score, breakdown: p.breakdown ?? {} } : null;
}

function SignalPanel({
  logs,
  stockNames,
}: {
  logs: LogEntry[];
  stockNames: Map<string, string>;
}) {
  const cci = parseCci(logs);
  const reliability = parseReliability(logs);
  const verdict = reliability ? reliabilityVerdict(reliability.score) : null;
  const signals = logs.filter((l) => l.event_type === "signal").slice(0, 6);

  return (
    <Panel title="전략 신호" bodyClassName="flex-none">
      <div className="grid md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section
          aria-label="CCI 멀티 타임프레임"
          className="border-b border-line p-4 md:border-b-0 md:border-r"
        >
          <h3 className="text-xs font-medium text-muted">
            CCI 멀티 타임프레임
          </h3>
          <dl className="num mt-3 grid grid-cols-4 divide-x divide-line">
            {(
              cci ??
              CCI_FRAMES.map((f) => ({
                ...f,
                value: null,
                signal: "neutral" as const,
                cross: null,
              }))
            ).map((tf) => (
              <div key={tf.key} className="px-3 first:pl-0">
                <dt className="text-xs text-muted">{tf.label}</dt>
                <dd
                  className={cn(
                    "mt-1 text-xl font-bold tracking-tight",
                    tf.value === null
                      ? "text-muted"
                      : CCI_SIGNAL[tf.signal].cls,
                  )}
                >
                  {tf.value !== null ? tf.value.toFixed(1) : "—"}
                </dd>
                <dd className="mt-0.5 text-xs text-dim">
                  {tf.value === null ? "대기" : CCI_SIGNAL[tf.signal].label}
                  {tf.cross === "golden" && " · 골든크로스"}
                  {tf.cross === "dead" && " · 데드크로스"}
                </dd>
              </div>
            ))}
          </dl>
          {!cci && (
            <p className="mt-3 text-xs leading-relaxed text-muted">
              전략 엔진이 CCI 스냅샷(cci_snapshot)을 보내면 타임프레임별 값이
              채워집니다.
            </p>
          )}
        </section>

        <section aria-label="신뢰도 스코어" className="p-4">
          <h3 className="text-xs font-medium text-muted">신뢰도 스코어</h3>
          <div className="num mt-3 flex items-baseline gap-2">
            <span
              className={cn(
                "text-xl font-bold tracking-tight",
                verdict?.cls ?? "text-muted",
              )}
            >
              {reliability ? reliability.score : "—"}
            </span>
            <span className="text-xs text-muted">/ {RELIABILITY_MAX}</span>
            {verdict && (
              <span
                className={cn("ml-auto text-data font-semibold", verdict.cls)}
              >
                {verdict.label}
              </span>
            )}
          </div>
          <div
            role="meter"
            aria-label="신뢰도 스코어"
            aria-valuenow={reliability?.score ?? 0}
            aria-valuemin={0}
            aria-valuemax={RELIABILITY_MAX}
            className="mt-2 grid grid-cols-8 gap-1"
          >
            {Array.from({ length: RELIABILITY_MAX }, (_, i) => (
              <span
                key={i}
                className={cn(
                  "h-1.5 rounded-sm",
                  reliability && i < reliability.score ? "bg-ink" : "bg-line",
                )}
              />
            ))}
          </div>
          {reliability && Object.keys(reliability.breakdown).length > 0 ? (
            <ul className="mt-3 space-y-1 text-xs">
              {Object.entries(reliability.breakdown).map(([key, passed]) => (
                <li key={key} className="flex items-center gap-2">
                  {passed ? (
                    <Check
                      aria-hidden="true"
                      className="h-3.5 w-3.5 text-ink"
                    />
                  ) : (
                    <Minus
                      aria-hidden="true"
                      className="h-3.5 w-3.5 text-muted"
                    />
                  )}
                  <span className="sr-only">{passed ? "충족" : "미충족"}</span>
                  <span className={passed ? "text-ink" : "text-muted"}>
                    {key}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-xs leading-relaxed text-muted">
              조건별 충족 여부는 스코어 이벤트(reliability_score)가 오면
              표시됩니다.
            </p>
          )}
        </section>
      </div>

      <section aria-label="최근 시그널" className="border-t border-line">
        <h3 className="px-4 pt-3 text-xs font-medium text-muted">
          최근 시그널
        </h3>
        {signals.length === 0 ? (
          <p className="px-4 pb-4 pt-2 text-xs text-muted">
            이번 세션에 발생한 시그널이 없습니다.
          </p>
        ) : (
          <ul className="num mt-1 divide-y divide-line/60 pb-1 text-data">
            {signals.map((l) => {
              const p = l.payload as {
                side?: "BUY" | "SELL";
                symbol?: string;
                price?: number;
              } | null;
              return (
                <li
                  key={l._key}
                  className="flex items-baseline gap-3 px-4 py-1.5"
                >
                  <time className="font-mono text-xs text-muted">
                    {fmtClock(l.timestamp)}
                  </time>
                  <span
                    className={cn(
                      "font-semibold",
                      p?.side === "BUY" ? "text-up" : "text-down",
                    )}
                  >
                    {p?.side ? SIDE_LABEL[p.side] : "—"}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-ink">
                    {p?.symbol ? stockLabel(p.symbol, stockNames) : ""}
                  </span>
                  <span className="text-dim">{p?.price?.toLocaleString()}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </Panel>
  );
}

// ============================================================================
// 백테스트
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
  const fieldId = useId();

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
    setStatusMsg("시작하는 중…");
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
          setStatusMsg(`실행 중… (${s.status})`);
        },
        1500,
        120_000,
        controller.signal,
      );

      if (res.status === "failed") {
        setError("백테스트가 실패했습니다. 종목코드와 기간을 확인해 주세요.");
      } else if (res.metrics) {
        setResult(res.metrics);
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.message.includes("취소")) return;
      setError(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setRunning(false);
    }
  }

  const metrics: { label: string; value: string; cls: string }[] = result
    ? [
        {
          label: "연환산 수익률",
          value: `${result.annualized_return >= 0 ? "+" : ""}${(result.annualized_return * 100).toFixed(1)}%`,
          cls: trendClass(result.annualized_return),
        },
        {
          label: "최대 낙폭 (MDD)",
          value: `-${Math.abs(result.mdd * 100).toFixed(1)}%`,
          cls: "text-down",
        },
        {
          label: "샤프 지수",
          value: result.sharpe_ratio.toFixed(2),
          cls: "text-ink",
        },
        {
          label: "승률",
          value: `${(result.win_rate * 100).toFixed(1)}%`,
          cls: "text-ink",
        },
        {
          label: "손익비",
          value: result.profit_loss_ratio.toFixed(2),
          cls: "text-ink",
        },
        {
          label: "총 거래",
          value: `${result.total_trades}회`,
          cls: "text-ink",
        },
      ]
    : [];

  return (
    <Panel title="백테스트">
      <form
        className="space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <div>
          <label
            htmlFor={`${fieldId}-symbol`}
            className="mb-1 block text-xs text-muted"
          >
            종목코드
          </label>
          <input
            id={`${fieldId}-symbol`}
            type="text"
            inputMode="numeric"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.trim())}
            className="field font-mono"
            placeholder="005930"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label
              htmlFor={`${fieldId}-start`}
              className="mb-1 block text-xs text-muted"
            >
              시작일
            </label>
            <input
              id={`${fieldId}-start`}
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="field"
            />
          </div>
          <div>
            <label
              htmlFor={`${fieldId}-end`}
              className="mb-1 block text-xs text-muted"
            >
              종료일
            </label>
            <input
              id={`${fieldId}-end`}
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="field"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={running || !symbol}
          className="btn btn-primary w-full"
        >
          {running ? (statusMsg ?? "실행 중…") : "백테스트 실행"}
        </button>
      </form>

      {error && <p className="state-err border-t">{error}</p>}

      {result ? (
        <dl className="num grid grid-cols-2 border-t border-line">
          {metrics.map(({ label, value, cls }, i) => (
            <div
              key={label}
              className={cn(
                "border-b border-line/60 px-4 py-3",
                i % 2 === 0 && "border-r",
              )}
            >
              <dt className="text-xs text-muted">{label}</dt>
              <dd className={cn("mt-0.5 text-base font-semibold", cls)}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        !error &&
        !running && (
          <p className="border-t border-line px-4 py-4 text-xs leading-relaxed text-muted">
            현재 전략을 과거 구간에 돌려 수익률·낙폭·승률을 확인합니다. 실계좌
            주문은 나가지 않습니다.
          </p>
        )
      )}
    </Panel>
  );
}

// ============================================================================
// 화면
// ============================================================================

interface Props {
  status: BotStatus | null;
  risk: RiskMetrics | null;
  logs: LogEntry[];
  connected: boolean;
  stockNames: Map<string, string>;
}

export function StrategyPage({
  status,
  risk,
  logs,
  connected,
  stockNames,
}: Props) {
  return (
    <div className="grid grid-cols-1 gap-3 xl:h-full xl:grid-cols-[340px_minmax(0,1fr)_340px]">
      <BotStatePanel status={status} risk={risk} />

      <div className="flex min-h-0 flex-col gap-3">
        <SignalPanel logs={logs} stockNames={stockNames} />
        <StreamLog
          logs={logs}
          connected={connected}
          stockNames={stockNames}
          dailyOrderCount={risk?.daily_order_count}
          className="min-h-64 flex-1"
        />
      </div>

      <BacktestPanel />
    </div>
  );
}
