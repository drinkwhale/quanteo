import { useState, useEffect } from "react";

interface GridLayouts {
  lg?: any[];
  md?: any[];
  sm?: any[];
}

const STORAGE_KEY = "dashboard-layout";

const DEFAULT_LAYOUT: GridLayouts = {
  lg: [
    { x: 0, y: 0, w: 12, h: 1, i: "indices" },
    { x: 0, y: 1, w: 7, h: 3, i: "market-stocks" },
    { x: 7, y: 1, w: 5, h: 3, i: "account-summary" },
    { x: 0, y: 4, w: 8, h: 4, i: "operations" },
    { x: 8, y: 4, w: 4, h: 4, i: "control" },
    { x: 0, y: 8, w: 12, h: 3, i: "strategy" },
  ],
  md: [
    { x: 0, y: 0, w: 10, h: 1, i: "indices" },
    { x: 0, y: 1, w: 10, h: 3, i: "market-stocks" },
    { x: 0, y: 4, w: 10, h: 3, i: "account-summary" },
    { x: 0, y: 7, w: 10, h: 4, i: "operations" },
    { x: 0, y: 11, w: 10, h: 3, i: "control" },
    { x: 0, y: 14, w: 10, h: 3, i: "strategy" },
  ],
  sm: [
    { x: 0, y: 0, w: 12, h: 1, i: "indices" },
    { x: 0, y: 1, w: 12, h: 3, i: "market-stocks" },
    { x: 0, y: 4, w: 12, h: 3, i: "account-summary" },
    { x: 0, y: 7, w: 12, h: 4, i: "operations" },
    { x: 0, y: 11, w: 12, h: 3, i: "control" },
    { x: 0, y: 14, w: 12, h: 3, i: "strategy" },
  ],
};

export function useGridLayout() {
  const [layouts, setLayouts] = useState<GridLayouts>(DEFAULT_LAYOUT);
  const [mounted, setMounted] = useState(false);

  // 로컬스토리지에서 레이아웃 로드
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        setLayouts(JSON.parse(saved));
      }
    } catch (err) {
      console.warn("Failed to load saved layout:", err);
    }
    setMounted(true);
  }, []);

  // 레이아웃 변경 시 저장
  const handleLayoutChange = (_newLayout: any[], newLayouts?: GridLayouts) => {
    if (newLayouts) {
      setLayouts(newLayouts);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(newLayouts));
      } catch (err) {
        console.warn("Failed to save layout:", err);
      }
    }
  };

  // 레이아웃 리셋
  const resetLayout = () => {
    setLayouts(DEFAULT_LAYOUT);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.warn("Failed to reset layout:", err);
    }
  };

  return {
    layouts,
    handleLayoutChange,
    resetLayout,
    mounted,
  };
}
