import { useState } from "react";

export interface PanelPosition {
  x: number | string;
  y: number | string;
  width: number | string;
  height: number | string;
}

export interface PanelPositions {
  [key: string]: PanelPosition;
}

interface UseGridLayoutReturn {
  positions: PanelPositions;
  updatePosition: (panelId: string, newPosition: PanelPosition) => void;
  resetLayout: () => void;
  mounted: boolean;
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

const loadSavedPositions = (): PanelPositions => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch {
    if (process.env.NODE_ENV === "development") {
      console.warn("Failed to load saved positions from localStorage");
    }
  }
  return DEFAULT_POSITIONS;
};

export function useGridLayout(): UseGridLayoutReturn {
  const [positions, setPositions] =
    useState<PanelPositions>(loadSavedPositions);
  const [mounted] = useState(true);

  const updatePosition = (panelId: string, newPosition: PanelPosition) => {
    setPositions((prev) => {
      const updated = { ...prev, [panelId]: newPosition };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        if (process.env.NODE_ENV === "development") {
          console.error("Failed to persist panel position:", panelId, err);
        }
      }
      return updated;
    });
  };

  const resetLayout = () => {
    setPositions(DEFAULT_POSITIONS);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      if (process.env.NODE_ENV === "development") {
        console.error("Failed to reset layout storage:", err);
      }
    }
  };

  return {
    positions,
    updatePosition,
    resetLayout,
    mounted,
  };
}
