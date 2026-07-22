import { createChart } from "lightweight-charts";
import { useEffect, useRef } from "react";
import { CandleItem } from "../../api/candles";

interface PriceChartProps {
  candles: CandleItem[];
  isLoading?: boolean;
  error?: Error | null;
}

export function PriceChart({ candles, isLoading, error }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // 차트 생성
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 400,
      layout: {
        background: { color: "#0f1117" },
        textColor: "#f1f5f9",
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      grid: {
        horzLines: {
          color: "#1f2630",
        },
        vertLines: {
          color: "#1f2630",
        },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: "#10b981",
          width: 1,
        },
        horzLine: {
          color: "#10b981",
          width: 1,
        },
      },
    });

    chartRef.current = chart;

    // 캔들 시리즈
    const candleSeries = (chart as any).addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    // 거래량 시리즈
    const volumeSeries = (chart as any).addHistogramSeries({
      color: "#6b7280",
      priceFormat: {
        type: "volume" as any,
      },
    });

    // 데이터 변환 및 설정
    if (candles.length > 0) {
      const candleData = candles.map((c) => ({
        time: new Date(c.timestamp).getTime() / 1000,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));

      const volumeData = candles.map((c) => ({
        time: new Date(c.timestamp).getTime() / 1000,
        value: c.volume,
        color: c.close >= c.open ? "#22c55e" : "#ef4444",
      }));

      candleSeries.setData(candleData);
      volumeSeries.setData(volumeData);

      // 차트 자동 스케일
      chart.timeScale().fitContent();
    }

    // 창 크기 변경 시 차트 리사이즈
    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [candles]);

  if (error) {
    return (
      <div className="w-full h-96 flex items-center justify-center bg-midnight-panel border border-border rounded text-alert-red">
        <p>차트 로드 실패: {error.message}</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="w-full h-96 flex items-center justify-center bg-midnight-panel border border-border rounded text-muted animate-pulse">
        로드 중...
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full border border-border rounded bg-midnight-panel"
    />
  );
}
