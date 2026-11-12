import {
  CandlestickSeries,
  createChart,
  CrosshairMode,
  HistogramSeries,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { CandleItem } from "../../api/candles";

interface PriceChartProps {
  candles: CandleItem[];
  isLoading?: boolean;
  error?: Error | null;
}

/** index.css의 R G B 트리플릿 토큰을 캔버스가 읽을 수 있는 rgba() 문자열로 바꾼다. */
function token(name: string, alpha = 1): string {
  const rgb = getComputedStyle(document.documentElement)
    .getPropertyValue(`--${name}`)
    .trim()
    .split(/\s+/)
    .join(", ");
  return `rgba(${rgb}, ${alpha})`;
}

export function PriceChart({ candles, isLoading, error }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const up = token("up");
    const down = token("down");

    // autoSize: 컨테이너 크기를 ResizeObserver로 따라간다 — 수동 resize 리스너 불필요
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: token("muted"),
        fontFamily: "Pretendard Variable, Pretendard, system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: token("line"),
      },
      rightPriceScale: { borderColor: token("line") },
      grid: {
        horzLines: { color: token("line", 0.6) },
        vertLines: { color: token("line", 0.6) },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: {
          color: token("muted"),
          labelBackgroundColor: token("raised"),
        },
        horzLine: {
          color: token("muted"),
          labelBackgroundColor: token("raised"),
        },
      },
    });

    // 국내 증시 관례: 양봉=빨강, 음봉=파랑
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: up,
      downColor: down,
      borderVisible: false,
      wickUpColor: up,
      wickDownColor: down,
    });
    candleSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.08, bottom: 0.26 },
    });

    // 거래량 (가격과 별도 스케일에 하단 오버레이로 표시)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      // 거래량 마지막 값 라벨이 가격 축 눈금과 겹쳐서 끈다
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    if (candles.length > 0) {
      // lightweight-charts는 시간 오름차순 정렬 필수
      const sorted = [...candles].sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      );
      const time = (c: CandleItem) =>
        (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp;

      candleSeries.setData(
        sorted.map((c) => ({
          time: time(c),
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      );
      volumeSeries.setData(
        sorted.map((c) => ({
          time: time(c),
          value: c.volume,
          color: token(c.close >= c.open ? "up" : "down", 0.45),
        })),
      );
      chart.timeScale().fitContent();
    }

    return () => chart.remove();
  }, [candles]);

  if (error) {
    return (
      <p className="state-err">차트를 불러오지 못했습니다 — {error.message}</p>
    );
  }

  return (
    <div className="relative h-full min-h-[320px]">
      <div
        ref={containerRef}
        className="absolute inset-0"
        role="img"
        aria-label="캔들 차트와 거래량"
      />
      {isLoading && (
        <p className="absolute inset-x-0 top-3 text-center text-xs text-muted">
          캔들 불러오는 중…
        </p>
      )}
      {!isLoading && candles.length === 0 && (
        <p className="absolute inset-0 flex items-center justify-center text-xs text-muted">
          이 기간에 캔들 데이터가 없습니다.
        </p>
      )}
    </div>
  );
}
