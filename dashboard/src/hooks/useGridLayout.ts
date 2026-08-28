import { useState, useEffect } from "react";

export interface PanelPosition {
  x: number | string;
  y: number | string;
  width: number | string;
  height: number | string;
}

export interface PanelPositions {
  [key: string]: PanelPosition;
}

const STORAGE_KEY = "dashboard-panel-positions";

const DEFAULT_POSITIONS: PanelPositions = {
  indices: { x: 0, y: 0, width: "100%", height: 100 },
  "market-stocks": { x: 0, y: 120, width: "calc(50% - 8px)", height: 350 },
  "account-summary": {
    x: "calc(50% + 8px)",
    y: 120,
    width: "calc(50% - 8px)",
    height: 350,
  },
  operations: { x: 0, y: 490, width: "calc(65% - 8px)", height: 400 },
  control: {
    x: "calc(65% + 8px)",
    y: 490,
    width: "calc(35% - 8px)",
    height: 400,
  },
  strategy: { x: 0, y: 910, width: "100%", height: 300 },
};

export function useGridLayout() {
  const [positions, setPositions] = useState<PanelPositions>(DEFAULT_POSITIONS);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        setPositions(JSON.parse(saved));
      }
    } catch (err) {
      console.warn("Failed to load saved positions:", err);
    }
    setMounted(true);
  }, []);

  const updatePosition = (panelId: string, newPosition: PanelPosition) => {
    setPositions((prev) => {
      const updated = { ...prev, [panelId]: newPosition };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        console.warn("Failed to save position:", err);
      }
      return updated;
    });
  };

  const resetLayout = () => {
    setPositions(DEFAULT_POSITIONS);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.warn("Failed to reset layout:", err);
    }
  };

  return {
    positions,
    updatePosition,
    resetLayout,
    mounted,
  };
}
