import { useMemo, useState } from "react";
import type { BalanceInfo, BalanceItem } from "../api/types";
import { fmtPnl, fmtPrice, pnlColorClass, toNumber } from "../lib/format";

interface Props {
  balance: BalanceInfo | null;
  error?: string | null;
  lastUpdated?: Date | null;
}

type SortKey = "eval_desc" | "name";
type DisplayMode = "eval" | "current";

const AVATAR_PALETTE = [
  "bg-red-500/15 text-red-400",
  "bg-amber-500/15 text-amber-400",
  "bg-accent/15 text-accent",
  "bg-emerald-500/15 text-emerald-400",
  "bg-violet-500/15 text-violet-400",
  "bg-orange-500/15 text-orange-400",
];

/** 실제 종목 로고가 없어 심볼 기반 결정론적 색상의 이니셜 아바타로 대체한다. */
function avatarStyle(symbol: string): string {
  let hash = 0;
  for (const ch of symbol) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function sortItems(items: BalanceItem[], key: SortKey): BalanceItem[] {
  const copy = [...items];
  if (key === "name") {
    copy.sort((a, b) => a.symbol_name.localeCompare(b.symbol_name, "ko"));
  } else {
    copy.sort((a, b) => toNumber(b.eval_amount) - toNumber(a.eval_amount));
  }
  return copy;
}

/**
 * 계좌 요약 — Toss 앱 "내 투자" 카드 레이아웃을 그대로 반영.
 * 예수금(원화·달러 현금)은 Toss holdings 응답에 포함되지 않아 항상 0으로만
 * 잡힌다 — 가짜 수치를 보여주지 않기 위해 이 카드에는 넣지 않았다.
 */
export function AccountSummary({ balance, error, lastUpdated }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("eval_desc");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("eval");

  const sorted = useMemo(
    () => sortItems(balance?.items ?? [], sortKey),
    [balance, sortKey],
  );

  if (error) {
    return (
      <p className="px-4 py-6 text-xs text-negative text-center">{error}</p>
    );
  }

  if (!balance) {
    return (
      <p className="px-4 py-6 text-xs text-muted text-center">불러오는 중...</p>
    );
  }

  const totalEval = toNumber(balance.total_eval_amount_krw);
  const totalPnl = toNumber(balance.total_profit_loss_krw);
  const costBasis = totalEval - totalPnl;
  // fmtPnl이 100을 곱해 표시하므로 여기서는 순수 비율(fraction)로 둔다.
  const totalRate = costBasis !== 0 ? totalPnl / costBasis : 0;

  return (
    <div className="p-4 space-y-4">
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted">내 투자</span>
          {lastUpdated && (
            <span className="flex items-center gap-1 text-[10px] text-muted tabular-nums">
              <span
                aria-hidden="true"
                className="inline-block w-1.5 h-1.5 rounded-full bg-positive animate-pulse"
              />
              {lastUpdated.toLocaleTimeString("ko-KR")} 기준
            </span>
          )}
        </div>
        <div className="text-2xl font-bold text-white tabular-nums tracking-tight mt-1">
          {fmtPrice(totalEval, "domestic")}
        </div>
        <div
          className={`text-sm font-semibold tabular-nums mt-0.5 ${pnlColorClass(totalPnl)}`}
        >
          {fmtPnl(totalPnl, totalRate, "domestic")}
        </div>
      </div>

      {sorted.length === 0 ? (
        <p className="text-xs text-muted">보유 종목 없음</p>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              aria-label="정렬 기준"
              className="bg-surface border border-border rounded px-2 py-1 text-muted focus-visible:outline-accent focus:text-white"
            >
              <option value="eval_desc">평가금액 높은순</option>
              <option value="name">이름순</option>
            </select>

            <div
              role="group"
              aria-label="표시 항목"
              className="flex rounded border border-border overflow-hidden flex-shrink-0"
            >
              {(["current", "eval"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={displayMode === mode}
                  onClick={() => setDisplayMode(mode)}
                  className={`px-2 py-1 transition-colors ${
                    displayMode === mode
                      ? "bg-accent/20 text-accent"
                      : "text-muted hover:text-white"
                  }`}
                >
                  {mode === "current" ? "현재가" : "평가금액"}
                </button>
              ))}
            </div>
          </div>

          <ul className="space-y-3">
            {sorted.map((item) => (
              <li key={item.symbol} className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className={`flex items-center justify-center w-9 h-9 rounded-full text-xs font-bold flex-shrink-0 ${avatarStyle(item.symbol)}`}
                >
                  {item.symbol_name.slice(0, 1)}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white font-semibold leading-snug line-clamp-2">
                    {item.symbol_name}
                  </div>
                  <div className="text-xs text-muted tabular-nums">
                    {toNumber(item.qty).toLocaleString()}주
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-sm font-semibold text-white tabular-nums">
                    {displayMode === "current"
                      ? fmtPrice(item.current_price, item.market)
                      : fmtPrice(item.eval_amount, item.market)}
                  </div>
                  <div
                    className={`text-xs tabular-nums ${pnlColorClass(item.profit_loss)}`}
                  >
                    {fmtPnl(
                      item.profit_loss,
                      item.profit_loss_rate,
                      item.market,
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="text-[10px] text-muted leading-relaxed border-t border-border pt-3">
        * 예수금(현금)은 아직 연동되지 않아 이 카드에는 표시하지 않습니다.
      </p>
    </div>
  );
}
