import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";

/**
 * 심볼 → 종목명 매핑을 세션 동안 캐시한다.
 * 종목 참조 정보는 영업일 단위로만 갱신되는 데이터라(Toss Stock Info 스펙 권고)
 * 포지션·주문처럼 폴링하지 않고, 아직 캐시에 없는 심볼이 새로 나타날 때만 조회한다.
 */
export function useStockNames(symbols: string[]): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());
  const knownRef = useRef<Set<string>>(new Set());

  const uniqueKey = useMemo(
    () =>
      Array.from(new Set(symbols.filter(Boolean)))
        .sort()
        .join(","),
    [symbols],
  );

  useEffect(() => {
    if (!uniqueKey) return;
    const unknown = uniqueKey
      .split(",")
      .filter((s) => !knownRef.current.has(s));
    if (unknown.length === 0) return;

    unknown.forEach((s) => knownRef.current.add(s));

    api
      .getStockNames(unknown)
      .then((res) => {
        setNames((prev) => {
          const next = new Map(prev);
          for (const item of res.items) next.set(item.symbol, item.name);
          return next;
        });
      })
      .catch(() => {
        // 조회 실패 — 캐시에서 제거해 다음 렌더에서 재시도 가능하게 둔다.
        // (화면에는 stockLabel()이 심볼 코드로 폴백해 계속 정상 표시된다.)
        unknown.forEach((s) => knownRef.current.delete(s));
      });
  }, [uniqueKey]);

  return names;
}
