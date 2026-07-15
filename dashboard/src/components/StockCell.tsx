interface Props {
  symbol: string;
  names: Map<string, string>;
}

/**
 * 종목 셀 — 종목명을 위에, 코드를 아래 보조 텍스트로 보여준다.
 * 이름을 아직 못 가져왔으면(로딩 중·조회 실패) 코드만 표시해 그대로 식별 가능하게 둔다.
 */
export function StockCell({ symbol, names }: Props) {
  const name = names.get(symbol);
  return (
    <div className="min-w-0">
      <div className="text-white font-semibold truncate">{name ?? symbol}</div>
      {name && (
        <div className="text-[10px] font-mono text-muted tabular-nums truncate">
          {symbol}
        </div>
      )}
    </div>
  );
}
