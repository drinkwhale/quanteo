import { useId, type ReactNode } from "react";
import { cn } from "../lib/utils";

type Props = {
  title: string;
  /** 제목 옆 보조 정보 — 건수, 기준 시각 등 */
  meta?: ReactNode;
  /** 헤더 우측 조작 요소 — 필터, 새로고침 등 */
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
};

/**
 * 화면의 유일한 컨테이너 어휘. 패널 안에 패널을 넣지 않는다 — 내부 구획은 구분선으로 나눈다.
 * 본문이 넘치면 패널 안에서 스크롤되고 헤더는 고정된다.
 */
export function Panel({
  title,
  meta,
  actions,
  className,
  bodyClassName,
  children,
}: Props) {
  const titleId = useId();

  return (
    <section
      aria-labelledby={titleId}
      className={cn(
        "flex min-h-0 min-w-0 flex-col rounded-lg border border-line bg-panel",
        className,
      )}
    >
      <header className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-4 py-1.5">
        <h2 id={titleId} className="text-sm font-semibold text-ink">
          {title}
        </h2>
        {meta !== undefined && (
          <span className="num text-xs text-muted">{meta}</span>
        )}
        {actions && (
          <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2">
            {actions}
          </div>
        )}
      </header>
      {/* relative: 본문 안 sr-only(absolute) 요소가 스크롤 영역 밖으로 빠져나가 문서 높이를 늘리지 않게 가둔다 */}
      <div
        className={cn("relative min-h-0 flex-1 overflow-auto", bodyClassName)}
      >
        {children}
      </div>
    </section>
  );
}
