import { fmtPrice, toNumber } from "../lib/format";
import type { PositionItem } from "../api/types";

interface Props {
  positions: PositionItem[];
}

interface MarketTotal {
  market: string;
  label: string;
  total: number;
}

function summarizeByMarket(positions: PositionItem[]): MarketTotal[] {
  const totals = new Map<string, number>();
  for (const p of positions) {
    totals.set(p.market, (totals.get(p.market) ?? 0) + toNumber(p.book_value));
  }
  return Array.from(totals.entries()).map(([market, total]) => ({
    market,
    label: market === "overseas" ? "해외" : "국내",
    total,
  }));
}

/**
 * 계좌 요약 — Toss 사이드바의 "내 투자" 카드에 대응.
 * 현재가 데이터가 없어 평가손익은 계산하지 않는다(가짜 수치 금지) — 매입원가(book_value) 합산만 노출.
 */
export function AccountSummary({ positions }: Props) {
  const marketTotals = summarizeByMarket(positions);

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-mono text-muted">보유 종목</span>
        <span className="text-sm font-mono font-bold text-white">
          {positions.length}종목
        </span>
      </div>

      {marketTotals.length === 0 ? (
        <p className="text-xs text-muted font-mono">매입금액 데이터 없음</p>
      ) : (
        <dl className="space-y-1.5">
          {marketTotals.map((m) => (
            <div
              key={m.market}
              className="flex items-baseline justify-between text-xs font-mono"
            >
              <dt className="text-muted">{m.label} 총 매입금액</dt>
              <dd className="text-accent font-bold">
                {fmtPrice(m.total, m.market)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <p className="text-[10px] font-mono text-muted leading-relaxed border-t border-border pt-3">
        * 평가손익은 실시간 현재가 연동 후 제공 예정 — 위 금액은 매입원가
        기준입니다.
      </p>
    </div>
  );
}
