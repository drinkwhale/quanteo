import { ChevronDown, GripVertical } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

type Props = {
  title: string;
  badge?: ReactNode;
  headerExtra?: ReactNode;
  defaultCollapsed?: boolean;
  className?: string;
  children: ReactNode;
};

/**
 * 상시 노출 멀티패널 대시보드의 공용 패널 셸.
 * 접기/펼치기는 로컬 state로만 관리 — 새로고침 시 초기화(영속화는 스코프 밖).
 */
export function Panel({
  title,
  badge,
  headerExtra,
  defaultCollapsed = false,
  className = "",
  children,
}: Props) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const contentId = useId();

  return (
    <section
      className={`bg-panel border border-border rounded-lg overflow-hidden ${className}`}
    >
      <div
        className={`flex items-center gap-1.5 px-3 py-2.5 ${collapsed ? "" : "border-b border-border"}`}
      >
        <GripVertical
          aria-hidden="true"
          className="w-3.5 h-3.5 flex-shrink-0 text-muted/50 cursor-grab"
        />
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
          aria-controls={contentId}
          className="flex items-center gap-2 flex-1 min-w-0 text-left focus-visible:outline-accent rounded"
        >
          <ChevronDown
            aria-hidden="true"
            className={`w-3.5 h-3.5 flex-shrink-0 text-muted transition-transform duration-150 ${
              collapsed ? "-rotate-90" : ""
            }`}
          />
          <h2 className="text-sm font-semibold text-white tracking-tight truncate">
            {title}
          </h2>
          {badge !== undefined && (
            <span className="text-xs text-muted flex-shrink-0 tabular-nums">
              {badge}
            </span>
          )}
        </button>
        {headerExtra && (
          <div className="flex-shrink-0 flex items-center gap-2">
            {headerExtra}
          </div>
        )}
      </div>

      {!collapsed && <div id={contentId}>{children}</div>}
    </section>
  );
}
