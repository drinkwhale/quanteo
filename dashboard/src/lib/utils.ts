import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 테이블 타임스탬프 셀 공용 className — PositionsTable/OrdersTable/FillsTable에서 재사용 */
export const TIMESTAMP_CELL_CLASS = "px-4 py-2 text-muted text-xs font-mono";
