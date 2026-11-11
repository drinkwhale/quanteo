import { useEffect, useState } from "react";

/**
 * 헤더·보조 지표용 단순 폴링. 실패하면 마지막 값을 지우고 null을 돌려준다 —
 * 화면에는 "—"로 나가서, 오래된 값을 최신인 것처럼 보여주지 않는다.
 * fetcher는 모듈 스코프 함수처럼 참조가 고정된 것을 넘길 것(매 렌더 새 함수면 폴링이 재시작된다).
 */
export function usePoll<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): T | null {
  const [data, setData] = useState<T | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = () =>
      fetcher()
        .then((d) => alive && setData(d))
        .catch(() => alive && setData(null));
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [fetcher, intervalMs]);

  return data;
}
