/**
 * OpenOrdersPanel - Zeigt offene Sell Orders als Tabelle
 */
import { formatEUR, formatBTC, formatDate } from '../utils/formatters';
import { useAppState } from '../contexts/AppStateContext';

const OpenOrdersPanel = ({ openOrders }) => {
  const { marketPrice } = useAppState();
  if (openOrders.length === 0) return null;

  return (
    <div className="open-orders-panel">
      <h3>Offene Sell Orders ({openOrders.length})</h3>
      <table className="open-orders-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Preis</th>
            <th>Menge</th>
            <th>Referenz</th>
            <th>Erstellt</th>
          </tr>
        </thead>
        <tbody>
          {openOrders.map((order) => {
            const belowMarket = parseFloat(order.price) <= marketPrice;
            return (
            <tr key={order.id} className={belowMarket ? 'order-row-warning' : ''}>
              <td><span className={`order-status-dot ${belowMarket ? 'warning' : 'open'}`} /> {order.status}</td>
              <td>
                {formatEUR(order.price)}
                {belowMarket && (
                  <span className="order-warning-badge" title={`Sell-Preis liegt unter dem Marktpreis (${formatEUR(marketPrice)})`}>
                    Unter Markt
                  </span>
                )}
              </td>
              <td>{formatBTC(order.quantity)}</td>
              <td className="order-id">
                {order.linked_lot_id
                  ? `Lot ${order.linked_lot_id.slice(0, 8)}...`
                  : order.linked_pairing_id
                    ? `Pairing ${order.linked_pairing_id.slice(0, 8)}...`
                    : '-'}
              </td>
              <td>{formatDate(order.created_at)}</td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default OpenOrdersPanel;
