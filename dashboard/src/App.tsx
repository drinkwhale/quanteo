import { ControlPanel } from "./components/ControlPanel";
import { OrdersTable } from "./components/OrdersTable";
import { PositionsTable } from "./components/PositionsTable";
import { StatusBar } from "./components/StatusBar";
import { StreamLog } from "./components/StreamLog";
import { useOrders } from "./hooks/useOrders";
import { usePositions } from "./hooks/usePositions";
import { useStatus } from "./hooks/useStatus";
import { useStream } from "./hooks/useStream";

export default function App() {
  const { status, refetch: refetchStatus } = useStatus(3000);
  const { positions, total: posTotal } = usePositions(5000);
  const { orders, total: ordTotal } = useOrders(5000);
  const { logs, connected } = useStream();

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      <StatusBar status={status} streamConnected={connected} />

      <main className="flex-1 p-4 grid grid-cols-1 xl:grid-cols-3 gap-4 auto-rows-min">
        {/* 왼쪽 2/3: 포지션·주문·스트림 */}
        <div className="xl:col-span-2 space-y-4">
          <PositionsTable positions={positions} total={posTotal} />
          <OrdersTable orders={orders} total={ordTotal} />
          <StreamLog logs={logs} connected={connected} />
        </div>

        {/* 오른쪽 1/3: 제어 패널 */}
        <div className="space-y-4">
          <ControlPanel status={status} onAction={refetchStatus} />
        </div>
      </main>
    </div>
  );
}
