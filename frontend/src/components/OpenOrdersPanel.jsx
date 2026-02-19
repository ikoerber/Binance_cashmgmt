/**
 * OpenOrdersPanel - Zeigt offene Sell Orders und Buy Orders als separate Tabellen
 */
import { formatQuote, formatBase, formatDate } from '../utils/formatters';
import { useSymbol } from '../contexts/SymbolContext';

const OpenOrdersPanel = ({ openOrders, openBuyOrders = [] }) => {
  const { symbol: activeSymbol, marketPrice } = useSymbol();
  if (openOrders.length === 0 && openBuyOrders.length === 0) return null;

  return (
    <>
      {openOrders.length > 0 && (
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
                    {formatQuote(order.price, activeSymbol)}
                    {belowMarket && (
                      <span className="order-warning-badge" title={`Sell-Preis liegt unter dem Marktpreis (${formatQuote(marketPrice, activeSymbol)})`}>
                        Unter Markt
                      </span>
                    )}
                  </td>
                  <td>{formatBase(order.quantity, activeSymbol)}</td>
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
      )}

      {openBuyOrders.length > 0 && (
        <div className="open-orders-panel open-orders-buy">
          <h3>Offene Buy Orders ({openBuyOrders.length})</h3>
          <table className="open-orders-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Typ</th>
                <th>Preis</th>
                <th>Menge</th>
                <th>Wert</th>
              </tr>
            </thead>
            <tbody>
              {openBuyOrders.map((order) => {
                const price = parseFloat(order.price);
                const qty = parseFloat(order.quantity);
                return (
                <tr key={order.id}>
                  <td><span className="order-status-dot open" /> {order.status}</td>
                  <td>{order.type}</td>
                  <td>{formatQuote(price, activeSymbol)}</td>
                  <td>{formatBase(qty, activeSymbol)}</td>
                  <td>{formatQuote(price * qty, activeSymbol)}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
};

export default OpenOrdersPanel;
