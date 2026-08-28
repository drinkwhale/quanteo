import { ReactNode } from "react";
import { Panel } from "./Panel";

interface DraggablePanelProps {
  id: string;
  title: string;
  badge?: ReactNode;
  headerExtra?: ReactNode;
  children: ReactNode;
}

export function DraggablePanel({
  id,
  title,
  badge,
  headerExtra,
  children,
}: DraggablePanelProps) {
  return (
    <div key={id} className="h-full">
      <Panel title={title} badge={badge} headerExtra={headerExtra}>
        {children}
      </Panel>
    </div>
  );
}
