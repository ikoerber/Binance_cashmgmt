/**
 * PairingPanel - Aufklappbarer Bereich für virtuelles Pairing
 *
 * 3 Tabs: Vorschläge (auto) | Manuell (Lot-Auswahl) | Bestehende Pairings
 * Simulation-Overlay (Pflicht vor Ausführung)
 */
import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPairingSuggestions,
  simulatePairing,
  createPairing,
  listPairings,
  lockPairing,
  unlockPairing,
  executePairing,
  deletePairing,
} from '../api/client';
import './PairingPanel.css';

const PairingPanel = ({
  userId,
  marketPrice,
  selectedLots,
  onClearSelection,
  onToggleLot,
  activeTab,
  onTabChange,
  onHighlightLots,
}) => {
  const queryClient = useQueryClient();

  // Suggestion parameters
  const [thresholdPct, setThresholdPct] = useState(5);

  // Manual pairing threshold
  const [manualThreshold, setManualThreshold] = useState(5);

  // Simulation state
  const [simulationData, setSimulationData] = useState(null);
  const [showSimulationModal, setShowSimulationModal] = useState(false);
  const [simulatingPairingId, setSimulatingPairingId] = useState(null);

  // Action feedback
  const [actionMessage, setActionMessage] = useState(null);

  // Existing pairings filter
  const [existingStatusFilter, setExistingStatusFilter] = useState(null);
  const [showExecuted, setShowExecuted] = useState(false);

  const showMessage = (type, text) => {
    setActionMessage({ type, text });
    setTimeout(() => setActionMessage(null), 5000);
  };

  // ─── Queries ───

  const {
    data: suggestionsData,
    isLoading: suggestionsLoading,
    refetch: refetchSuggestions,
  } = useQuery({
    queryKey: ['pairingSuggestions', userId, marketPrice, thresholdPct],
    queryFn: () => getPairingSuggestions(userId, marketPrice, thresholdPct / 100),
    enabled: activeTab === 'suggestions' && !!marketPrice,
    refetchInterval: 60000,
  });

  const {
    data: existingData,
    isLoading: existingLoading,
    refetch: refetchExisting,
  } = useQuery({
    queryKey: ['pairings', userId, existingStatusFilter],
    queryFn: () => listPairings(userId, existingStatusFilter),
    enabled: activeTab === 'existing',
    refetchInterval: 30000,
  });

  // ─── Mutations ───

  const createMutation = useMutation({
    mutationFn: ({ items, threshold }) => createPairing(userId, items, threshold),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      showMessage('success', 'Pairing erstellt (DRAFT)');
      onClearSelection();
      onTabChange('existing');
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const lockMutation = useMutation({
    mutationFn: (pairingId) => lockPairing(userId, pairingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      showMessage('success', 'Pairing gesperrt (LOCKED)');
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const unlockMutation = useMutation({
    mutationFn: (pairingId) => unlockPairing(userId, pairingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      showMessage('success', 'Pairing entsperrt (DRAFT)');
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const executeMutation = useMutation({
    mutationFn: (pairingId) => executePairing(userId, pairingId, marketPrice),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      queryClient.invalidateQueries({ queryKey: ['lots'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      setSimulationData(null);
      const lotCount = data?.lot_count || 0;
      showMessage('success', `Pairing ausgeführt: 1 Order (${lotCount} Lots aggregiert) auf Binance platziert`);
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (pairingId) => deletePairing(userId, pairingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      setSimulationData(null);
      showMessage('success', 'Pairing gelöscht');
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  // ─── Handlers ───

  const handleSimulate = async (pairingId) => {
    setSimulatingPairingId(pairingId);
    try {
      const result = await simulatePairing(userId, pairingId, marketPrice);
      setSimulationData({ ...result, pairing_id: pairingId });
      setShowSimulationModal(true);
    } catch (error) {
      showMessage('error', error.response?.data?.detail || error.message);
    } finally {
      setSimulatingPairingId(null);
    }
  };

  const handleCreateFromSelection = () => {
    if (selectedLots.length === 0) return;
    const items = selectedLots.map((lot) => ({
      lot_id: lot.id,
      qty_btc: parseFloat(lot.qty_btc_open),
    }));
    createMutation.mutate({ items, threshold: manualThreshold / 100 });
  };

  const handleCreateFromSuggestion = (suggestion) => {
    const items = suggestion.items.map((item) => ({
      lot_id: item.lot_id,
      qty_btc: parseFloat(item.qty_btc),
    }));
    createMutation.mutate({ items, threshold: thresholdPct / 100 });
  };

  const handleExecute = (pairingId) => {
    if (!simulationData || simulationData.pairing_id !== pairingId) {
      showMessage('error', 'Bitte zuerst Simulation durchführen!');
      return;
    }
    if (window.confirm('Pairing wirklich ausführen? Orders werden auf Binance platziert.')) {
      executeMutation.mutate(pairingId);
    }
  };

  // ─── Computed Values ───

  const manualPreview = useMemo(() => {
    if (selectedLots.length === 0) return null;
    const totalCost = selectedLots.reduce((sum, lot) => sum + parseFloat(lot.break_even) * parseFloat(lot.qty_btc_open), 0);
    const totalQty = selectedLots.reduce((sum, lot) => sum + parseFloat(lot.qty_btc_open), 0);
    const totalValue = totalQty * marketPrice;
    const netPnl = totalValue - totalCost;
    const netPnlPct = totalCost > 0 ? (netPnl / totalCost) * 100 : 0;
    return { totalCost, totalQty, totalValue, netPnl, netPnlPct };
  }, [selectedLots, marketPrice]);

  // ─── Helpers ───

  const fmt = (num, decimals = 2) =>
    parseFloat(num).toLocaleString('de-DE', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });

  const fmtEUR = (num) => `${fmt(num)} \u20ac`;
  const fmtBTC = (num) => `${fmt(num, 8)} BTC`;

  // ─── Render ───

  return (
    <div className="pairing-panel">
      {/* Tabs */}
      <div className="pairing-tabs">
        <button
          className={activeTab === 'suggestions' ? 'active' : ''}
          onClick={() => onTabChange('suggestions')}
        >
          Vorschläge
        </button>
        <button
          className={activeTab === 'manual' ? 'active' : ''}
          onClick={() => onTabChange('manual')}
        >
          Manuell{selectedLots.length > 0 && ` (${selectedLots.length})`}
        </button>
        <button
          className={activeTab === 'existing' ? 'active' : ''}
          onClick={() => onTabChange('existing')}
        >
          Bestehende Pairings
        </button>
      </div>

      {/* Action Feedback */}
      {actionMessage && (
        <div className={`pairing-message pairing-${actionMessage.type}`}>
          {actionMessage.text}
          <button onClick={() => setActionMessage(null)}>&times;</button>
        </div>
      )}

      {/* ═══ Tab: Vorschläge ═══ */}
      {activeTab === 'suggestions' && (
        <div className="pairing-tab-content">
          <div className="pairing-controls">
            <div className="filter-group">
              <span className="filter-label">Zielmarge %</span>
              <input
                type="number"
                value={thresholdPct}
                onChange={(e) => setThresholdPct(parseFloat(e.target.value) || 5)}
                step="0.5"
                min="0"
                max="100"
              />
            </div>
            <button className="btn-refresh" onClick={() => refetchSuggestions()}>
              Neu laden
            </button>
          </div>

          {suggestionsLoading ? (
            <div className="pairing-empty">Lade Vorschläge...</div>
          ) : (suggestionsData?.suggestions || []).length === 0 ? (
            <div className="pairing-empty">
              Keine Pairing-Vorschläge bei aktueller Zielmarge.
            </div>
          ) : (
            <div className="pairing-cards">
              {suggestionsData.suggestions.map((s, idx) => {
                const pnlPct = parseFloat(s.net_pnl_pct) * 100;
                return (
                  <div
                    key={s.id || idx}
                    className="pairing-card"
                    onMouseEnter={() => onHighlightLots(new Set(s.items.map((item) => item.lot_id)))}
                    onMouseLeave={() => onHighlightLots(new Set())}
                  >
                    <div className="pairing-card-header">
                      <span className="pairing-card-title">
                        {s.items.length} Lots
                      </span>
                      <span className={`pairing-pnl ${pnlPct >= 0 ? 'profit' : 'loss'}`}>
                        {pnlPct >= 0 ? '+' : ''}{fmt(pnlPct)}%
                      </span>
                    </div>
                    <div className="pairing-card-details">
                      <div>
                        <span className="label">Netto BTC</span><br />
                        {fmt(s.net_qty_btc, 8)}
                      </div>
                      <div>
                        <span className="label">Netto Kosten</span><br />
                        {fmtEUR(s.net_cost)}
                      </div>
                      <div>
                        <span className="label">Netto P&L</span><br />
                        {fmtEUR(s.net_pnl_eur)}
                      </div>
                      <div>
                        <span className="label">Marktwert</span><br />
                        {fmtEUR(s.net_value)}
                      </div>
                    </div>
                    <div className="pairing-card-lots">
                      {s.items.map((item) => (
                        <span key={item.lot_id} className="lot-chip" title={item.lot_id}>
                          {item.lot_id.slice(0, 8)}...
                        </span>
                      ))}
                    </div>
                    <div className="pairing-card-actions">
                      <button
                        className="btn-create-from-suggestion"
                        onClick={() => handleCreateFromSuggestion(s)}
                        disabled={createMutation.isPending}
                      >
                        {createMutation.isPending ? 'Erstelle...' : 'Als Pairing speichern'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ═══ Tab: Manuell ═══ */}
      {activeTab === 'manual' && (
        <div className="pairing-tab-content">
          {selectedLots.length === 0 ? (
            <div className="pairing-empty">
              Wähle Lots in der Tabelle per Checkbox aus, um ein manuelles Pairing zu erstellen.
            </div>
          ) : (
            <>
              <div className="manual-preview">
                <div className="summary-card">
                  <span className="summary-label">Ausgewählte Lots</span>
                  <span className="summary-value">{selectedLots.length}</span>
                </div>
                <div className="summary-card">
                  <span className="summary-label">Gesamt BTC</span>
                  <span className="summary-value">{fmtBTC(manualPreview.totalQty)}</span>
                </div>
                <div className="summary-card">
                  <span className="summary-label">Gesamt Kosten</span>
                  <span className="summary-value">{fmtEUR(manualPreview.totalCost)}</span>
                </div>
                <div className={`summary-card ${manualPreview.netPnl >= 0 ? 'summary-profit' : 'summary-loss'}`}>
                  <span className="summary-label">Netto P&L</span>
                  <span className="summary-value">
                    {fmtEUR(manualPreview.netPnl)} ({manualPreview.netPnlPct >= 0 ? '+' : ''}{fmt(manualPreview.netPnlPct)}%)
                  </span>
                </div>
              </div>

              <table className="selected-lots-table">
                <thead>
                  <tr>
                    <th>Lot</th>
                    <th>Menge Offen</th>
                    <th>Break-even</th>
                    <th>P&L %</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {selectedLots.map((lot) => {
                    const pnlPct = ((marketPrice / parseFloat(lot.break_even)) - 1) * 100;
                    return (
                      <tr key={lot.id}>
                        <td className="order-id">
                          {lot.binance_order_id || lot.id.slice(0, 12) + '...'}
                        </td>
                        <td>{fmtBTC(lot.qty_btc_open)}</td>
                        <td>{fmtEUR(lot.break_even)}</td>
                        <td className={pnlPct >= 0 ? 'profit' : 'loss'}>
                          {pnlPct >= 0 ? '+' : ''}{fmt(pnlPct)}%
                        </td>
                        <td>
                          <button
                            className="btn-remove-lot"
                            onClick={() => onToggleLot(lot.id)}
                            title="Entfernen"
                          >
                            &times;
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div className="manual-actions">
                <div className="filter-group">
                  <span className="filter-label">Zielmarge %</span>
                  <input
                    type="number"
                    value={manualThreshold}
                    onChange={(e) => setManualThreshold(parseFloat(e.target.value) || 5)}
                    step="0.5"
                    min="0"
                    max="100"
                  />
                </div>
                <button
                  className="btn-create-pairing"
                  onClick={handleCreateFromSelection}
                  disabled={createMutation.isPending || selectedLots.length === 0}
                >
                  {createMutation.isPending ? 'Erstelle...' : 'Pairing erstellen'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══ Tab: Bestehende Pairings ═══ */}
      {activeTab === 'existing' && (
        <div className="pairing-tab-content">
          <div className="pairing-controls">
            <div className="filter-group">
              <span className="filter-label">Status</span>
              <select
                value={existingStatusFilter || ''}
                onChange={(e) => setExistingStatusFilter(e.target.value || null)}
                style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, minHeight: 38, background: 'white', cursor: 'pointer' }}
              >
                <option value="">Alle</option>
                <option value="DRAFT">Draft</option>
                <option value="LOCKED">Locked</option>
                <option value="EXECUTED">Executed</option>
              </select>
            </div>
            <label className="toggle-label">
              <span className="toggle-switch">
                <input
                  type="checkbox"
                  checked={showExecuted}
                  onChange={(e) => setShowExecuted(e.target.checked)}
                />
                <span className="toggle-slider" />
              </span>
              Ausgeführte anzeigen
            </label>
            <button className="btn-refresh" onClick={() => refetchExisting()}>
              Neu laden
            </button>
          </div>

          {existingLoading ? (
            <div className="pairing-empty">Lade Pairings...</div>
          ) : (() => {
            const filtered = (existingData?.pairings || []).filter(
              (p) => showExecuted || p.status !== 'EXECUTED'
            );
            return filtered.length === 0 ? (
              <div className="pairing-empty">Keine Pairings vorhanden.</div>
            ) : (
            <div className="pairing-cards">
              {filtered.map((p) => (
                <div
                  key={p.id}
                  className={`pairing-card ${p.status.toLowerCase()}`}
                  onMouseEnter={() => onHighlightLots(new Set(p.items.map((item) => item.lot_id)))}
                  onMouseLeave={() => onHighlightLots(new Set())}
                >
                  <div className="pairing-card-header">
                    <span className="pairing-card-title">
                      <span className={`status-badge ${p.status.toLowerCase()}`}>
                        {p.status}
                      </span>
                      {p.items.length} Lots
                    </span>
                    <span className="pairing-pnl">
                      {fmt(parseFloat(p.threshold_pct) * 100)}%
                    </span>
                  </div>
                  <div className="pairing-card-details">
                    <div>
                      <span className="label">Netto BTC</span><br />
                      {fmt(p.net_qty_btc, 8)}
                    </div>
                    <div>
                      <span className="label">Netto Kosten</span><br />
                      {fmtEUR(p.net_cost)}
                    </div>
                    {p.created_at && (
                      <div>
                        <span className="label">Erstellt</span><br />
                        {new Date(p.created_at).toLocaleDateString('de-DE')}
                      </div>
                    )}
                  </div>
                  <div className="pairing-card-lots">
                    {p.items.map((item) => (
                      <span key={item.lot_id} className="lot-chip" title={item.lot_id}>
                        {item.lot_id.slice(0, 8)}...
                      </span>
                    ))}
                  </div>
                  <div className="pairing-card-actions">
                    {p.status === 'DRAFT' && (
                      <>
                        <button
                          className="btn-simulate"
                          onClick={() => handleSimulate(p.id)}
                          disabled={simulatingPairingId === p.id}
                        >
                          {simulatingPairingId === p.id ? 'Simuliere...' : 'Simulation'}
                        </button>
                        <button
                          className="btn-lock"
                          onClick={() => lockMutation.mutate(p.id)}
                          disabled={lockMutation.isPending}
                        >
                          Sperren
                        </button>
                        <button
                          className="btn-delete"
                          onClick={() => {
                            if (window.confirm('Pairing wirklich löschen?')) {
                              deleteMutation.mutate(p.id);
                            }
                          }}
                          disabled={deleteMutation.isPending}
                        >
                          Löschen
                        </button>
                      </>
                    )}
                    {p.status === 'LOCKED' && (
                      <>
                        <button
                          className="btn-simulate"
                          onClick={() => handleSimulate(p.id)}
                          disabled={simulatingPairingId === p.id}
                        >
                          {simulatingPairingId === p.id ? 'Simuliere...' : 'Simulation ansehen'}
                        </button>
                        <button
                          className="btn-unlock"
                          onClick={() => unlockMutation.mutate(p.id)}
                          disabled={unlockMutation.isPending}
                        >
                          {unlockMutation.isPending ? 'Entsperre...' : 'Entsperren'}
                        </button>
                        <button
                          className="btn-execute"
                          onClick={() => handleExecute(p.id)}
                          disabled={executeMutation.isPending}
                        >
                          {executeMutation.isPending ? 'Ausführen...' : 'Ausführen'}
                        </button>
                      </>
                    )}
                    {p.status === 'EXECUTED' && (
                      <span className="executed-label">Ausgeführt</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
            );
          })()}
        </div>
      )}

      {/* ═══ Simulation Overlay ═══ */}
      {simulationData && showSimulationModal && (
        <div className="simulation-overlay" onClick={() => setShowSimulationModal(false)}>
          <div className="simulation-preview" onClick={(e) => e.stopPropagation()}>
            <div className="simulation-header">
              <h3>Simulation Preview</h3>
              <button className="btn-close" onClick={() => setShowSimulationModal(false)}>
                &times;
              </button>
            </div>

            <div className="simulation-grid">
              <div className="sim-card">
                <span className="sim-label">Marktpreis</span>
                <span className="sim-value">{fmtEUR(simulationData.market_price)}</span>
              </div>
              <div className="sim-card">
                <span className="sim-label">BTC zu verkaufen</span>
                <span className="sim-value">{fmtBTC(simulationData.total_btc_to_sell)}</span>
              </div>
              <div className="sim-card">
                <span className="sim-label">Erwarteter Erlös</span>
                <span className="sim-value">{fmtEUR(simulationData.expected_proceeds_eur)}</span>
              </div>
              <div className="sim-card">
                <span className="sim-label">Kosten</span>
                <span className="sim-value">{fmtEUR(simulationData.expected_costs_eur)}</span>
              </div>
              <div className="sim-card">
                <span className="sim-label">Geschätzte Gebühren</span>
                <span className="sim-value">
                  {fmtEUR(simulationData.estimated_fee_eur)} ({fmt(parseFloat(simulationData.fee_pct) * 100)}%)
                </span>
              </div>
              <div className={`sim-card ${parseFloat(simulationData.expected_realized_pnl_eur) >= 0 ? 'sim-profit' : 'sim-loss'}`}>
                <span className="sim-label">Realisierte P&L</span>
                <span className="sim-value">{fmtEUR(simulationData.expected_realized_pnl_eur)}</span>
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
                    <td>{fmtBTC(lot.qty_btc_to_sell)}</td>
                    <td>{fmtBTC(lot.qty_btc_remaining)}</td>
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
              <span>Verbleibendes Portfolio: {fmtBTC(simulationData.remaining_portfolio_btc)}</span>
              <span>Verbleibende Kosten: {fmtEUR(simulationData.remaining_portfolio_cost_eur)}</span>
            </div>

            {/* Geplante Binance Order (aggregiert) */}
            {simulationData.planned_orders && simulationData.planned_orders.length > 0 && (
              <>
                <h4>Geplante Binance Order</h4>

                {simulationData.has_max_value_violation && (
                  <div className="sim-warning">
                    Achtung: Der Orderwert ueberschreitet das Maximum
                    von {fmtEUR(simulationData.max_order_value_eur)}.
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
                        <span className="sim-value">{fmtBTC(order.quantity)}</span>
                      </div>
                      <div className="sim-card">
                        <span className="sim-label">Preis (EUR)</span>
                        <span className="sim-value">{fmtEUR(order.price)}</span>
                      </div>
                      <div className="sim-card">
                        <span className="sim-label">Stop-Preis</span>
                        <span className="sim-value">{fmtEUR(order.stopPrice)}</span>
                      </div>
                      <div className={`sim-card ${order.exceeds_max_order_value ? 'sim-loss' : ''}`}>
                        <span className="sim-label">Orderwert (EUR)</span>
                        <span className="sim-value">
                          {fmtEUR(order.order_value_eur)}
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
                  <span>Max. Orderwert: {fmtEUR(simulationData.max_order_value_eur)}</span>
                </div>
              </>
            )}

            <div className="simulation-actions">
              <button className="btn-close-sim" onClick={() => setShowSimulationModal(false)}>
                Schließen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PairingPanel;
