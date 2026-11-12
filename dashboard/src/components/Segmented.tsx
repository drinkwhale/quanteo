import { cn } from "../lib/utils";

type Option<T extends string> = {
  value: T;
  label: string;
  count?: number;
};

type Props<T extends string> = {
  /** 스크린리더용 그룹 이름 */
  label: string;
  options: readonly Option<T>[];
  value: T;
  onChange: (value: T) => void;
};

/** 같은 데이터를 다른 기준으로 볼 때 쓰는 세그먼트 토글 — 정렬·필터·봉 주기 전부 이걸로 통일. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: Props<T>) {
  return (
    <div
      role="group"
      aria-label={label}
      className="no-scrollbar inline-flex max-w-full overflow-x-auto rounded-md border border-line bg-canvas p-0.5"
    >
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={isActive}
            onClick={() => onChange(option.value)}
            className={cn(
              "h-6 whitespace-nowrap rounded px-2.5 text-xs font-medium transition-colors duration-150",
              isActive ? "bg-raised text-ink" : "text-muted hover:text-ink",
            )}
          >
            {option.label}
            {option.count !== undefined && (
              <span className="num ml-1.5 opacity-70">{option.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
