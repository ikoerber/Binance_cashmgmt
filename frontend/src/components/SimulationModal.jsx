/**
 * SimulationModal - Simulation Preview Overlay fuer Pairings
 *
 * Zeigt Simulation-Details und erlaubt das Anpassen des Verkaufspreises.
 */
import { useState } from 'react';
import { formatNumber, formatQuote, formatBase } from '../utils/formatters';
import { useSymbol } from '../contexts/SymbolContext';
import { getQuoteLabel, getBaseLabel } from '../utils/symbolRegistry';

const SimulationModal = ({ simulationData, onClose, onResimulate }) => {
  const { symbol: activeSymbol } = useSymbol();
  const fmtBase = (num) => formatBase(num, activeSymbol);
  const fmtQuote = (num) => formatQuote(num, activeSymbol);
  const quoteLabel = getQuoteLabel(activeSymbol);

  if (!simulationData) return null;

  // Aktuellen Sell-Preis aus planned_orders extrahieren
  const currentSellPrice = simulationData.planned_orders?.[0]?.price
    ? parseFloat(simulationData.planned_orders[0].price)
    : null;

  const [customPrice, setCustomPrice] = useState(
    currentSellPrice ? currentSellPrice.toFixed(2) : ''
  );
  const [isResimulating, setIsResimulating] = useState(false);

  const handleResimulate = async () => {
    const price = parseFloat(customPrice);
    if (!price || price <= 0 || isNaN(price)) return;
    if (!onResimulate) return;

    setIsResimulating(true);
    try {
      await onResimulate(price);
    } finally {
      setIsResimulating(false);
    }
  };

  // Preis hat sich gegenueber dem berechneten Default geaendert?
  const defaultPrice = simulationData.market_price
    ? parseFloat(simulationData.market_price) * (1 + parseFloat(simulationData.fee_buffer_pct || 0.002))
    : null;
  const isCustom = customPrice && defaultPrice
    ? Math.abs(parseFloat(customPrice) - defaultPrice) > 0.01
    : false;

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
            <span className="sim-value">{fmtQuote(simulationData.market_price)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">BTC zu verkaufen</span>
            <span className="sim-value">{fmtBase(simulationData.total_base_to_sell)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">Erwarteter Erloes</span>
            <span className="sim-value">{fmtQuote(simulationData.expected_proceeds_quote)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">Kosten</span>
            <span className="sim-value">{fmtQuote(simulationData.expected_costs_quote)}</span>
          </div>
          <div className="sim-card">
            <span className="sim-label">Geschaetzte Gebuehren</span>
            <span className="sim-value">
              {fmtQuote(simulationData.estimated_fee_quote)} ({formatNumber(parseFloat(simulationData.fee_pct) * 100)}%)
            </span>
          </div>
          <div className={`sim-card ${parseFloat(simulationData.expected_realized_pnl_quote) >= 0 ? 'sim-profit' : 'sim-loss'}`}>
            <span className="sim-label">Realisierte P&L</span>
            <span className="sim-value">{fmtQuote(simulationData.expected_realized_pnl_quote)}</span>
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
                <td>{fmtBase(lot.qty_base_to_sell)}</td>
                <td>{fmtBase(lot.qty_base_remaining)}</td>
                <td>
                  <span className={`status-badge ${lot.new_status.toLowerCase()}`}>
                    {lot.new_status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sim-hint">
          Der angezeigte Status tritt erst ein, wenn die Sell-Order auf Binance ausgefuehrt (filled) wird.
          Bis dahin bleibt der aktuelle Lot-Status unveraendert.
        </p>

        <div className="simulation-remaining">
          <span>Verbleibendes Portfolio: {fmtBase(simulationData.remaining_portfolio_base)}</span>
          <span>Verbleibende Kosten: {fmtQuote(simulationData.remaining_portfolio_cost_quote)}</span>
        </div>

        {simulationData.planned_orders && simulationData.planned_orders.length > 0 && (
          <>
            <h4>Geplante Binance Order</h4>

            {simulationData.has_max_value_violation && (
              <div className="sim-warning">
                Achtung: Der Orderwert ueberschreitet das Maximum
                von {fmtQuote(simulationData.max_order_value_quote)}.
                Die Ausfuehrung wird fehlschlagen.
              </div>
            )}

            <div className="sell-price-editor">
              <label className="sell-price-label">
                Verkaufspreis ({quoteLabel})
                {isCustom && <span className="custom-badge">Angepasst</span>}
              </label>
              <div className="sell-price-input-row">
                <input
                  type="number"
                  className="sell-price-input"
                  value={customPrice}
                  onChange={(e) => setCustomPrice(e.target.value)}
                  step="0.01"
                  min="0"
                />
                {onResimulate && (
                  <button
                    className="btn-resimulate"
                    onClick={handleResimulate}
                    disabled={isResimulating || !customPrice || parseFloat(customPrice) <= 0}
                  >
                    {isResimulating ? 'Berechne...' : 'Neu berechnen'}
                  </button>
                )}
                {isCustom && (
                  <button
                    className="btn-reset-price"
                    onClick={() => {
                      setCustomPrice(defaultPrice ? defaultPrice.toFixed(2) : '');
                      if (onResimulate) onResimulate(null);
                    }}
                    title="Auf Standardpreis zuruecksetzen"
                  >
                    Reset
                  </button>
                )}
              </div>
            </div>

            {simulationData.planned_orders.map((order, idx) => (
              <div key={idx} className={`planned-order-card ${order.exceeds_max_order_value ? 'order-exceeds-max' : ''}`}>
                <div className="simulation-grid">
                  <div className="sim-card">
                    <span className="sim-label">Typ</span>
                    <span className="sim-value" style={{ fontSize: 14 }}>{order.type}</span>
                  </div>
                  <div className="sim-card">
                    <span className="sim-label">Menge ({getBaseLabel(activeSymbol)})</span>
                    <span className="sim-value">{fmtBase(order.quantity)}</span>
                  </div>
                  <div className="sim-card">
                    <span className="sim-label">Preis ({quoteLabel})</span>
                    <span className="sim-value">{fmtQuote(order.price)}</span>
                  </div>
                  <div className="sim-card">
                    <span className="sim-label">Stop-Preis</span>
                    <span className="sim-value">{fmtQuote(order.stopPrice)}</span>
                  </div>
                  <div className={`sim-card ${order.exceeds_max_order_value ? 'sim-loss' : ''}`}>
                    <span className="sim-label">Orderwert ({quoteLabel})</span>
                    <span className="sim-value">
                      {fmtQuote(order.order_value_quote)}
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
              <span>Max. Orderwert: {fmtQuote(simulationData.max_order_value_quote)}</span>
            </div>
          </>
        )}

        <div className="simulation-actions">
          <button className="btn-close-sim" onClick={onClose}>
            Schliessen
          </button>
        </div>
      </div>
    </div>
  );
};

export default SimulationModal;
