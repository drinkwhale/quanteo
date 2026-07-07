import type { IndexQuoteItem } from "../api/types";
import { fmtIndexChange, fmtIndexPrice, pnlColorClass } from "../lib/format";

interface Props {
  indices: IndexQuoteItem[];
  error?: string | null;
}

/**
 * 주요 지수·환율 — 코스피·코스닥·나스닥·달러/원·엔/원.
 * Toss Open API에는 지수·해외환율 엔드포인트가 없어 외부 소스(Yahoo Finance)에서
 * 가져온다(core/marketdata/index_quotes.py) — 계좌·주문과 달리 실시간 트레이딩용이
 * 아닌 참고용 데이터라 30초 지연은 문제되지 않는다.
 *
 * gap-px + bg-border 트릭으로 헤어라인 구분선을 그린다 — divide-x/y는 그리드가
 * 줄바꿈되는 순간(항목 5개 이상) 줄 끝/시작에 구분선이 어색하게 남는 문제가 있다.
 */
export function IndicesStrip({ indices, error }: Props) {
  if (error) {
    return (
      <p className="px-4 py-6 text-xs text-negative text-center">{error}</p>
    );
  }

  if (indices.length === 0) {
    return (
      <p className="px-4 py-6 text-xs text-muted text-center">불러오는 중...</p>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-px bg-border">
      {indices.map((idx) => (
        <div key={idx.key} className="bg-panel p-4 space-y-1">
          <div className="text-xs text-muted truncate">{idx.label}</div>
          <div className="text-lg font-bold text-white tabular-nums tracking-tight">
            {fmtIndexPrice(idx.price)}
          </div>
          <div
            className={`text-xs font-semibold tabular-nums ${pnlColorClass(idx.change)}`}
          >
            {fmtIndexChange(idx.change, idx.change_rate)}
          </div>
        </div>
      ))}
    </div>
  );
}
