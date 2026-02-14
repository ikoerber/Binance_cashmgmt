/**
 * SimulationModal - Simulation Preview Overlay fuer Pairings
 */
import { formatNumber, formatEUR, formatBTC } from '../utils/formatters';

const SimulationModal = ({ simulationData, onClose }) => {
  if (!simulationData) return null;

  return (
    <div className="simulation-overlay" onClick={onClose}>
      <div className="simulation-preview" onClick={(e) => e.stopPropagation()}>
        <div className="simulation-header">
          <h3>Simulation Preview</h3>
          <button className="btn-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="simulation-grid">
          <div className="sim-card">
            <span className="sim-label">Marktpreis</span>
            <span className="sim-value">{formatEUR(simulationData.market_price)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">BTC zu verkaufen</span>
            <span className="sim-value">{formatBTC(simulationData.total_btc_to_sell)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">Erwarteter Erlös</span>
            <span className="sim-value">{formatEUR(simulationData.expected_proceeds_eur)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">Kosten</span>
            <span className="sim-value">{formatEUR(simulationData.expected_costs_eur)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">Geschätzte Gebühren</span>
            <span className="sim-value">
              {formatEUR(simulationData.estimated_fee_eur)} ({formatNumber(parseFloat(simulationData.fee_pct) * 100)}%)
            </span>
          </div>
          <div className={`sim-card ${parseFloat(simulationData.expected_realized_pnl_eur) >= 0 ? 'sim-profit' : 'sim-loss'}`}>
            <span className="sim-label">Realisierte P&L</span>
            <span className="sim-value">{formatEUR(simulationData.expected_realized_pnl_eur)}</span>
          </div>
        </div>

        <h4>Betroffene Lots</h4>
        <table className="affected-lots-table">
          <thead>
            <tr>
              <th>Lot</th>
              <th>Menge zu verkaufen</th>
              <th>Verbleibend</th>
              <th>Neuer Status</th>
            </tr>
          </thead>
          <tbody>
            {(simulationData.affected_lots || []).map((lot) => (
              <tr key={lot.lot_id}>
                <td className="order-id">{lot.lot_id.slice(0, 12)}...</td>
                <td>{formatBTC(lot.qty_btc_to_sell)}</td>
                <td>{formatBTC(lot.qty_btc_remaining)}</td>
                <td>
                  <span className={`status-badge ${lot.new_status.toLowerCase()}`}>
                    {lot.new_status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="simulation-remaining">
          <span>Verbleibendes Portfolio: {formatBTC(simulationData.remaining_portfolio_btc)}</span>
          <span>Verbleibende Kosten: {formatEUR(simulationData.remaining_portfolio_cost_eur)}</span>
        </div>

        {simulationData.planned_orders && simulationData.planned_orders.length > 0 && (
          <>
            <h4>Geplante Binance Order</h4>

            {simulationData.has_max_value_violation && (
              <div className="sim-warning">
                Achtung: Der Orderwert ueberschreitet das Maximum
                von {formatEUR(simulationData.max_order_value_eur)}.
                Die Ausfuehrung wird fehlschlagen.
              </div>
            )}

            {simulationData.planned_orders.map((order, idx) => (
              <div key={idx} className={`planned-order-card ${order.exceeds_max_order_value ? 'order-exceeds-max' : ''}`}>
                <div className="simulation-grid">
                  <div className="sim-card">
                    <span className="sim-label">Typ</span>
                    <span className="sim-value" style={{ fontSize: 14 }}>{order.type}</span>
                  </div>
                  <div className="sim-card">
                    <span className="sim-label">Menge (BTC)</span>
                    <span className="sim-value">{formatBTC(order.quantity)}</span>
                  </div>
                  <div className="sim-card">
                    <span className="sim-label">Preis (EUR)</span>
                    <span className="sim-value">{formatEUR(order.price)}</span>
                  </div>
                  <div className="sim-card">
                    <span className="sim-label">Stop-Preis</span>
                    <span className="sim-value">{formatEUR(order.stopPrice)}</span>
                  </div>
                  <div className={`sim-card ${order.exceeds_max_order_value ? 'sim-loss' : ''}`}>
                    <span className="sim-label">Orderwert (EUR)</span>
                    <span className="sim-value">
                      {formatEUR(order.order_value_eur)}
                      {order.exceeds_max_order_value && ' !!'}
                    </span>
                  </div>
                  <div className="sim-card">
                    <span className="sim-label">Lots</span>
                    <span className="sim-value" style={{ fontSize: 14 }}>{order.lot_count} Lots aggregiert</span>
                  </div>
                </div>
                <div className="client-order-id-row">
                  <span className="sim-label">Client Order ID: </span>
                  <span className="order-id" title={order.newClientOrderId}>{order.newClientOrderId}</span>
                </div>
              </div>
            ))}

            <div className="order-params-summary">
              <span>Fee-Buffer: {(parseFloat(simulationData.fee_buffer_pct) * 100).toFixed(1)}%</span>
              <span>Max. Orderwert: {formatEUR(simulationData.max_order_value_eur)}</span>
            </div>
          </>
        )}

        <div className="simulation-actions">
          <button className="btn-close-sim" onClick={onClose}>
            Schließen
          </button>
        </div>
      </div>
    </div>
  );
};

export default SimulationModal;
