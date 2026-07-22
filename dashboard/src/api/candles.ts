export interface CandleItem {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleList {
  items: CandleItem[];
}

export async function getCandles(
  symbol: string,
  interval: "1m" | "1d" = "1d",
  count: number = 100,
  before?: string,
  adjusted: boolean = true,
): Promise<CandleList> {
  const params = new URLSearchParams({
    symbol,
    interval,
    count: String(count),
    adjusted: String(adjusted),
  });

  if (before) {
    params.append("before", before);
  }

  const response = await fetch(`/api/candles?${params.toString()}`);

  if (!response.ok) {
    throw new Error(`캔들 조회 실패: ${response.status}`);
  }

  return response.json();
}
