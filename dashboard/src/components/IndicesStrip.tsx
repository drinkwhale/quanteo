import type { IndexQuoteItem } from "../api/types";
import { fmtIndexChange, fmtIndexPrice, trendClass } from "../lib/format";

interface Props {
  indices: IndexQuoteItem[];
  error?: string | null;
}

/**
 * 주요 지수·환율 띠 — 코스피·코스닥·나스닥·달러/원·엔/원.
 * Toss Open API에는 지수·해외환율 엔드포인트가 없어 외부 소스(Yahoo Finance)에서
 * 가져온다(core/marketdata/index_quotes.py) — 참고용 데이터라 30초 지연은 문제되지 않는다.
 * 시장 맥락은 "흘끗" 보는 정보라 패널을 차지하지 않고 한 줄 띠로만 둔다.
 */
export function IndicesStrip({ indices, error }: Props) {
  return (
    <div
      role="region"
      aria-label="주요 지수·환율"
      tabIndex={0}
      className="no-scrollbar flex min-h-9 items-center overflow-x-auto border-b border-line px-4 text-xs"
    >
      {error ? (
        <span className="text-danger">지수 조회 실패 — {error}</span>
      ) : indices.length === 0 ? (
        <span className="text-muted">지수 불러오는 중…</span>
      ) : (
        <ul className="num flex items-center">
          {indices.map((idx) => (
            <li
              key={idx.key}
              className="mr-5 flex shrink-0 items-baseline gap-2 border-r border-line pr-5 last:mr-0 last:border-0 last:pr-0"
            >
              <span className="text-muted">{idx.label}</span>
              <span className="font-semibold text-ink">
                {fmtIndexPrice(idx.price)}
              </span>
              <span className={trendClass(idx.change)}>
                {fmtIndexChange(idx.change, idx.change_rate)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
