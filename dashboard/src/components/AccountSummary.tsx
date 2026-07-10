import { useMemo, useState } from "react";
import type { BalanceInfo, BalanceItem } from "../api/types";
import { calcSellFees, type SellFeeResult } from "../lib/fees";
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
 * "현재가" 모드는 전일 종가 대비 당일 등락(day_change)을, "평가금액" 모드는
 * 매입가 기준 누적 수익률(profit_loss_rate)을 보여준다 — 서로 다른 축이라
 * 잘못 섞어 쓰면 "두 모드가 같은 숫자로 나온다"는 버그가 된다(과거에 실제
 * 있었던 버그). day_change는 캔들 조회가 실패하면 null이니, 그 경우
 * profit_loss로 조용히 대체하지 않고 결측을 그대로 보여준다.
 *
 * feeAdjusted가 주어지면(평가금액 모드 + 수수료·세금 포함 토글 ON + 국내 종목)
 * 매도 시뮬레이션 기준 손익·수익률로 대체한다 — 화면에 보이는 평가금액이
 * 수수료 차감분이면 그 아래 손익도 같은 기준이어야 숫자가 앞뒤로 맞는다.
 */
function PnlDelta({
  item,
  displayMode,
  feeAdjusted,
}: {
  item: BalanceItem;
  displayMode: DisplayMode;
  feeAdjusted?: { profitLoss: number; rate: number } | null;
}) {
  if (displayMode === "eval") {
    const profitLoss = feeAdjusted ? feeAdjusted.profitLoss : item.profit_loss;
    const rate = feeAdjusted ? feeAdjusted.rate : item.profit_loss_rate;
    return (
      <div className={`text-xs tabular-nums ${pnlColorClass(profitLoss)}`}>
        {fmtPnl(profitLoss, rate, item.market)}
      </div>
    );
  }

  if (!item.day_change) {
    return <div className="text-xs text-muted">당일 등락 조회 실패</div>;
  }

  return (
    <div
      className={`text-xs tabular-nums ${pnlColorClass(item.day_change.amount)}`}
    >
      {fmtPnl(item.day_change.amount, item.day_change.rate, item.market)}
    </div>
  );
}

/**
 * 매도 수수료·세금을 반영한 손익·수익률을 계산한다.
 * costBasis(매입원가)는 item.eval_amount - item.profit_loss로 역산한다 —
 * 백엔드가 avg_price*qty를 그대로 안 내려주는 경우가 있어 손익 기준으로
 * 역산하는 편이 항상 정확하다(총합 카드의 costBasis 계산과 동일한 방식).
 */
function computeFeeAdjustedPnl(
  item: BalanceItem,
  fees: SellFeeResult,
): { profitLoss: number; rate: number } {
  const profitLoss = toNumber(item.profit_loss) - fees.commission - fees.tax;
  const costBasis = toNumber(item.eval_amount) - toNumber(item.profit_loss);
  const rate = costBasis !== 0 ? profitLoss / costBasis : 0;
  return { profitLoss, rate };
}

/** 거래수수료·제세금을 분리 표기한다 — 하나로 합쳐 보여주면 사용자가 각 항목의
 * 근거(요율)를 검증할 수 없어서 항상 나눠서 보여준다. */
function FeeBreakdown({
  commission,
  tax,
  market,
}: {
  commission: number;
  tax: number;
  market: string;
}) {
  return (
    <div className="text-[10px] text-muted tabular-nums">
      수수료 -{fmtPrice(commission, market)} · 세금 -{fmtPrice(tax, market)}
    </div>
  );
}

/**
 * 계좌 요약 — Toss 앱 "내 투자" 카드 레이아웃을 그대로 반영.
 * 예수금(원화·달러 현금)은 Toss holdings 응답에 포함되지 않아 항상 0으로만
 * 잡힌다 — 가짜 수치를 보여주지 않기 위해 이 카드에는 넣지 않았다.
 */
export function AccountSummary({ balance, error, lastUpdated }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("eval_desc");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("eval");
  // 수수료·제세금은 KRX 요율 근사치라 국내 종목에만 의미가 있다(lib/fees.ts 참고).
  const [includeFees, setIncludeFees] = useState(false);

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

  // "현재가" 모드에서는 토글 버튼 자체가 숨겨져 있으니(아래 JSX 참고)
  // includeFees가 true로 남아 있어도 실제로 적용하면 안 된다 — 그러지 않으면
  // 모드를 바꿔도 총합 숫자가 수수료 반영 상태로 붙박여 있고 끌 방법도
  // 없어지는 상태가 된다(과거에 실제 있었던 버그).
  const effectiveIncludeFees = displayMode === "eval" && includeFees;

  // 총 수수료·세금은 국내 종목분만 합산한다 — total_eval_amount_krw는
  // 국내·해외 통합값이라 해외 종목에 KRX 요율을 적용하면 안 되기 때문.
  const domesticEval = balance.items
    .filter((item) => item.market === "domestic")
    .reduce((sum, item) => sum + toNumber(item.eval_amount), 0);
  const totalFees = calcSellFees(domesticEval);
  const displayTotalEval = effectiveIncludeFees
    ? totalEval - totalFees.commission - totalFees.tax
    : totalEval;
  // 수수료를 평가금액에서만 빼고 손익은 그대로 두면 "평가금액은 줄었는데
  // 수익률은 그대로"인 앞뒤 안 맞는 화면이 된다 — 손익도 같은 수수료만큼
  // 줄이고 수익률을 그 기준으로 다시 계산한다.
  const displayTotalPnl = effectiveIncludeFees
    ? totalPnl - totalFees.commission - totalFees.tax
    : totalPnl;
  // fmtPnl이 100을 곱해 표시하므로 여기서는 순수 비율(fraction)로 둔다.
  const displayTotalRate = costBasis !== 0 ? displayTotalPnl / costBasis : 0;

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
          {fmtPrice(displayTotalEval, "domestic")}
        </div>
        <div
          className={`text-sm font-semibold tabular-nums mt-0.5 ${pnlColorClass(displayTotalPnl)}`}
        >
          {fmtPnl(displayTotalPnl, displayTotalRate, "domestic")}
        </div>
        {effectiveIncludeFees && domesticEval > 0 && (
          <FeeBreakdown
            commission={totalFees.commission}
            tax={totalFees.tax}
            market="domestic"
          />
        )}
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

          {displayMode === "eval" && (
            <button
              type="button"
              aria-pressed={includeFees}
              onClick={() => setIncludeFees((v) => !v)}
              title="국내 종목에 KRX 요율(수수료 0.015%·제세금 0.2%) 근사 적용 — 실제 체결 거래소는 조회되지 않음"
              className={`self-start text-[11px] px-2 py-1 rounded border transition-colors ${
                includeFees
                  ? "bg-accent/20 text-accent border-accent/40"
                  : "text-muted border-border hover:text-white"
              }`}
            >
              수수료·세금 포함
            </button>
          )}

          <ul className="space-y-3">
            {sorted.map((item) => {
              const showItemFees =
                effectiveIncludeFees && item.market === "domestic";
              const itemFees = showItemFees
                ? calcSellFees(toNumber(item.eval_amount))
                : null;
              const feeAdjustedPnl = itemFees
                ? computeFeeAdjustedPnl(item, itemFees)
                : null;

              return (
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
                        : fmtPrice(
                            itemFees?.netAmount ?? item.eval_amount,
                            item.market,
                          )}
                    </div>
                    <PnlDelta
                      item={item}
                      displayMode={displayMode}
                      feeAdjusted={feeAdjustedPnl}
                    />
                    {itemFees && (
                      <FeeBreakdown
                        commission={itemFees.commission}
                        tax={itemFees.tax}
                        market={item.market}
                      />
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}

      <p className="text-[10px] text-muted leading-relaxed border-t border-border pt-3">
        * 예수금(현금)은 아직 연동되지 않아 이 카드에는 표시하지 않습니다.
      </p>
    </div>
  );
}
