import { ReactNode, useState } from "react";
import { Rnd } from "react-rnd";
import { PanelPosition } from "../hooks/useGridLayout";

interface RndPanelProps {
  id: string;
  title: string;
  children: ReactNode;
  position: PanelPosition;
  onPositionChange: (id: string, pos: PanelPosition) => void;
  headerExtra?: ReactNode;
}

export function RndPanel({
  id,
  title,
  children,
  position,
  onPositionChange,
  headerExtra,
}: RndPanelProps) {
  const [isDragging, setIsDragging] = useState(false);

  const parseNumericValue = (
    val: number | string,
    fallback: number,
  ): number => {
    if (typeof val === "number") return val;
    const parsed = parseInt(String(val), 10);
    return !isNaN(parsed) && parsed > 0 ? parsed : fallback;
  };

  const x = parseNumericValue(position.x, 0);
  const y = parseNumericValue(position.y, 0);
  const width = parseNumericValue(position.width, 400);
  const height = parseNumericValue(position.height, 250);

  return (
    <Rnd
      default={{
        x,
        y,
        width,
        height,
      }}
      position={{ x, y }}
      size={{
        width,
        height,
      }}
      onDragStart={() => setIsDragging(true)}
      onDragStop={(_e, d) => {
        try {
          onPositionChange(id, {
            x: d.x,
            y: d.y,
            width,
            height,
          });
        } catch (err) {
          if (process.env.NODE_ENV === "development") {
            console.error("Failed to update position on drag:", err);
          }
        } finally {
          setIsDragging(false);
        }
      }}
      onResizeStop={(_e, _direction, ref, _delta, pos) => {
        if (!ref || !ref.offsetWidth || !ref.offsetHeight) {
          if (process.env.NODE_ENV === "development") {
            console.warn("Invalid ref dimensions for resize:", {
              offsetWidth: ref?.offsetWidth,
              offsetHeight: ref?.offsetHeight,
            });
          }
          return;
        }

        try {
          onPositionChange(id, {
            x: pos.x,
            y: pos.y,
            width: ref.offsetWidth,
            height: ref.offsetHeight,
          });
        } catch (err) {
          if (process.env.NODE_ENV === "development") {
            console.error("Failed to update position on resize:", err);
          }
        }
      }}
      minWidth={200}
      minHeight={80}
      dragHandleClassName="rnd-drag-handle"
      style={{ zIndex: isDragging ? 1000 : 10 }}
    >
      <div className="bg-panel rounded-lg border border-border overflow-hidden h-full flex flex-col">
        <div className="rnd-drag-handle cursor-move px-4 py-3 border-b border-border/50 hover:bg-muted/5">
          <h3 className="text-xs font-sans font-semibold text-muted tracking-wider flex items-center justify-between">
            {title}
            {headerExtra && <div>{headerExtra}</div>}
          </h3>
        </div>
        <div className="flex-1 overflow-auto p-4">{children}</div>
      </div>
    </Rnd>
  );
}
