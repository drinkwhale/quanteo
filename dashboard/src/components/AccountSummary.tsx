import { useMemo, useState } from "react";
import type { BalanceInfo, BalanceItem } from "../api/types";
import { calcSellFees, type SellFeeResult } from "../lib/fees";
import {
  fmtClock,
  fmtPnl,
  fmtPrice,
  toNumber,
  trendClass,
} from "../lib/format";
import { cn } from "../lib/utils";
import { Panel } from "./Panel";
import { Segmented } from "./Segmented";

interface Props {
  balance: BalanceInfo | null;
  error?: string | null;
  lastUpdated?: Date | null;
  /** 원화 주문가능금액(/risk-metrics). 조회 실패·미연동이면 null → "—" */
  buyingPower?: number | string | null;
  className?: string;
}

type SortKey = "eval_desc" | "pnl_rate" | "name";

const SORT_OPTIONS = [
  { value: "eval_desc", label: "평가금액순" },
  { value: "pnl_rate", label: "수익률순" },
  { value: "name", label: "이름순" },
] as const;

function sortItems(items: BalanceItem[], key: SortKey): BalanceItem[] {
  const copy = [...items];
  if (key === "name") {
    copy.sort((a, b) => a.symbol_name.localeCompare(b.symbol_name, "ko"));
  } else if (key === "pnl_rate") {
    copy.sort((a, b) => b.profit_loss_rate - a.profit_loss_rate);
  } else {
    copy.sort((a, b) => toNumber(b.eval_amount) - toNumber(a.eval_amount));
  }
  return copy;
}

/**
 * 매도 수수료·세금을 반영한 손익·수익률을 계산한다.
 * costBasis(매입원가)는 item.eval_amount - item.profit_loss로 역산한다 —
 * 백엔드가 avg_price*qty를 그대로 안 내려주는 경우가 있어 손익 기준으로
 * 역산하는 편이 항상 정확하다(총합의 costBasis 계산과 동일한 방식).
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
    <div className="text-2xs text-muted">
      수수료 -{fmtPrice(commission, market)} · 세금 -{fmtPrice(tax, market)}
    </div>
  );
}

function Stat({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-base font-semibold text-ink">{children}</dd>
    </div>
  );
}

/**
 * 계좌 — 총합 한 줄 + 보유 종목 표.
 * 누적 손익(profit_loss, 매입가 기준)과 당일 등락(day_change, 전일 종가 기준)은 서로 다른
 * 축이라 열을 따로 둔다. 과거에 둘을 한 자리에서 토글로 바꿔 보여주다 같은 숫자가 나오는
 * 버그가 있었다 — 한 열에 섞지 말 것.
 */
export function AccountSummary({
  balance,
  error,
  lastUpdated,
  buyingPower,
  className,
}: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("eval_desc");
  // 수수료·제세금은 KRX 요율 근사치라 국내 종목에만 의미가 있다(lib/fees.ts 참고).
  const [includeFees, setIncludeFees] = useState(false);

  const sorted = useMemo(
    () => sortItems(balance?.items ?? [], sortKey),
    [balance, sortKey],
  );

  const meta = lastUpdated ? `${fmtClock(lastUpdated)} 기준` : undefined;

  if (error || !balance) {
    return (
      <Panel title="계좌" meta={meta} className={className}>
        {error ? (
          <p className="state-err">계좌 조회 실패 — {error}</p>
        ) : (
          <p className="state-msg">계좌 불러오는 중…</p>
        )}
      </Panel>
    );
  }

  const totalEval = toNumber(balance.total_eval_amount_krw);
  const totalPnl = toNumber(balance.total_profit_loss_krw);
  const costBasis = totalEval - totalPnl;

  // 총 수수료·세금은 국내 종목분만 합산한다 — total_eval_amount_krw는
  // 국내·해외 통합값이라 해외 종목에 KRX 요율을 적용하면 안 되기 때문.
  const domesticEval = balance.items
    .filter((item) => item.market === "domestic")
    .reduce((sum, item) => sum + toNumber(item.eval_amount), 0);
  const totalFees = calcSellFees(domesticEval);
  const totalFeeAmount = includeFees ? totalFees.commission + totalFees.tax : 0;
  const displayTotalEval = totalEval - totalFeeAmount;
  // 수수료를 평가금액에서만 빼고 손익은 그대로 두면 "평가금액은 줄었는데
  // 수익률은 그대로"인 앞뒤 안 맞는 화면이 된다 — 손익도 같은 수수료만큼
  // 줄이고 수익률을 그 기준으로 다시 계산한다.
  const displayTotalPnl = totalPnl - totalFeeAmount;
  // fmtPnl이 100을 곱해 표시하므로 여기서는 순수 비율(fraction)로 둔다.
  const displayTotalRate = costBasis !== 0 ? displayTotalPnl / costBasis : 0;

  return (
    <Panel
      title="계좌"
      meta={meta}
      className={className}
      actions={
        <>
          <button
            type="button"
            aria-pressed={includeFees}
            onClick={() => setIncludeFees((v) => !v)}
            title="국내 종목에 KRX 요율(수수료 0.015%·제세금 0.2%) 근사 적용 — 실제 체결 거래소는 조회되지 않음"
            className={cn(
              "btn h-7 px-2.5",
              includeFees && "border-ink bg-raised text-ink",
            )}
          >
            수수료·세금 포함
          </button>
          <Segmented
            label="정렬 기준"
            options={SORT_OPTIONS}
            value={sortKey}
            onChange={setSortKey}
          />
        </>
      }
    >
      <dl className="num flex flex-wrap items-end gap-x-10 gap-y-3 border-b border-line px-4 py-3.5">
        <div>
          <dt className="text-xs text-muted">총 평가금액</dt>
          <dd className="mt-0.5 text-2xl font-bold leading-8 tracking-tight text-ink">
            {fmtPrice(displayTotalEval, "domestic")}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">평가손익</dt>
          <dd
            className={cn(
              "mt-0.5 text-base font-semibold",
              trendClass(displayTotalPnl),
            )}
          >
            {fmtPnl(displayTotalPnl, displayTotalRate, "domestic")}
          </dd>
          {includeFees && domesticEval > 0 && (
            <FeeBreakdown
              commission={totalFees.commission}
              tax={totalFees.tax}
              market="domestic"
            />
          )}
        </div>
        <Stat label="매입금액">{fmtPrice(costBasis, "domestic")}</Stat>
        <Stat label="주문가능">
          {buyingPower == null ? "—" : fmtPrice(buyingPower, "domestic")}
        </Stat>
        <Stat label="보유">{balance.items.length}종목</Stat>
      </dl>

      {sorted.length === 0 ? (
        <p className="state-msg">
          보유 종목이 없습니다. 봇이 진입하면 이 표에 포지션이 나타납니다.
        </p>
      ) : (
        <table className="tbl">
          <thead>
            <tr>
              <th scope="col">종목</th>
              <th scope="col" className="r">
                보유
              </th>
              <th scope="col" className="r">
                평단가
              </th>
              <th scope="col" className="r">
                현재가
              </th>
              <th scope="col" className="r">
                당일 등락
              </th>
              <th scope="col" className="r">
                평가금액
              </th>
              <th scope="col" className="r">
                평가손익
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((item) => {
              const itemFees =
                includeFees && item.market === "domestic"
                  ? calcSellFees(toNumber(item.eval_amount))
                  : null;
              const pnl = itemFees
                ? computeFeeAdjustedPnl(item, itemFees)
                : {
                    profitLoss: toNumber(item.profit_loss),
                    rate: item.profit_loss_rate,
                  };

              return (
                <tr key={item.symbol}>
                  <td>
                    <div className="font-semibold text-ink">
                      {item.symbol_name}
                    </div>
                    <div className="font-mono text-2xs text-muted">
                      {item.symbol}
                    </div>
                  </td>
                  <td className="r text-dim">
                    {toNumber(item.qty).toLocaleString()}주
                  </td>
                  <td className="r text-dim">
                    {fmtPrice(item.avg_price, item.market)}
                  </td>
                  <td className="r font-semibold text-ink">
                    {fmtPrice(item.current_price, item.market)}
                  </td>
                  {/* day_change는 캔들 조회가 실패하면 null — 누적 손익으로 조용히
                      대체하지 않고 결측을 그대로 보여준다 */}
                  {item.day_change ? (
                    <td className={cn("r", trendClass(item.day_change.amount))}>
                      {fmtPnl(
                        item.day_change.amount,
                        item.day_change.rate,
                        item.market,
                      )}
                    </td>
                  ) : (
                    <td className="r text-muted" title="당일 등락 조회 실패">
                      <span aria-hidden="true">—</span>
                      <span className="sr-only">당일 등락 조회 실패</span>
                    </td>
                  )}
                  <td className="r text-ink">
                    {fmtPrice(
                      itemFees?.netAmount ?? item.eval_amount,
                      item.market,
                    )}
                  </td>
                  <td
                    className={cn(
                      "r font-semibold",
                      trendClass(pnl.profitLoss),
                    )}
                  >
                    {fmtPnl(pnl.profitLoss, pnl.rate, item.market)}
                    {itemFees && (
                      <FeeBreakdown
                        commission={itemFees.commission}
                        tax={itemFees.tax}
                        market={item.market}
                      />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
