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
  const x = typeof position.x === "number" ? position.x : 0;
  const y = typeof position.y === "number" ? position.y : 0;

  return (
    <Rnd
      key={id}
      default={{
        x,
        y,
        width: position.width,
        height: position.height,
      }}
      position={{ x, y }}
      size={{
        width: position.width,
        height: position.height,
      }}
      onDragStart={() => setIsDragging(true)}
      onDragStop={(_e, d) => {
        setIsDragging(false);
        onPositionChange(id, {
          x: d.x,
          y: d.y,
          width: position.width,
          height: position.height,
        });
      }}
      onResizeStop={(_e, _direction, ref, _delta, pos) => {
        onPositionChange(id, {
          x: pos.x,
          y: pos.y,
          width: ref.offsetWidth,
          height: ref.offsetHeight,
        });
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
