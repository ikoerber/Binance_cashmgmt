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
  createPairing,
} from '../api/client';
import { formatNumber, formatQuote, formatBase } from '../utils/formatters';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import useNotification from '../hooks/useNotification';
import PairingExistingTab from './PairingExistingTab';
import './PairingPanel.css';

const PairingPanel = ({
  selectedLots,
  onClearSelection,
  onToggleLot,
  activeTab,
  onTabChange,
  onHighlightLots,
}) => {
  const { userId } = useUser();
  const { symbol: activeSymbol, marketPrice } = useSymbol();
  const queryClient = useQueryClient();
  const { message: actionMessage, showMessage, dismissMessage } = useNotification();

  // Suggestion parameters
  const [thresholdPct, setThresholdPct] = useState(5);

  // Manual pairing threshold
  const [manualThreshold, setManualThreshold] = useState(5);

  // ─── Queries ───

  const {
    data: suggestionsData,
    isLoading: suggestionsLoading,
    refetch: refetchSuggestions,
  } = useQuery({
    queryKey: ['pairingSuggestions', activeSymbol, userId, marketPrice, thresholdPct],
    queryFn: () => getPairingSuggestions(
      userId, marketPrice, thresholdPct / 100, activeSymbol
    ),
    enabled: activeTab === 'suggestions' && !!marketPrice,
    refetchInterval: 60000,
  });

  // ─── Mutations ───

  const createMutation = useMutation({
    mutationFn: ({ items, threshold }) => createPairing(userId, items, threshold, activeSymbol),
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

  // ─── Handlers ───

  const handleCreateFromSelection = () => {
    if (selectedLots.length === 0) return;
    const items = selectedLots.map((lot) => ({
      lot_id: lot.id,
      qty_base: String(lot.qty_base_open),
    }));
    createMutation.mutate({
      items,
      threshold: String(manualThreshold / 100),
    });
  };

  const handleCreateFromSuggestion = (suggestion) => {
    const items = suggestion.items.map((item) => ({
      lot_id: item.lot_id,
      qty_base: String(item.qty_base),
    }));
    createMutation.mutate({
      items,
      threshold: String(thresholdPct / 100),
    });
  };

  // ─── Computed Values ───

  const manualPreview = useMemo(() => {
    if (selectedLots.length === 0) return null;
    const totalCost = selectedLots.reduce((sum, lot) => sum + parseFloat(lot.break_even) * parseFloat(lot.qty_base_open), 0);
    const totalQty = selectedLots.reduce((sum, lot) => sum + parseFloat(lot.qty_base_open), 0);
    const totalValue = totalQty * marketPrice;
    const netPnl = totalValue - totalCost;
    const netPnlPct = totalCost > 0 ? (netPnl / totalCost) * 100 : 0;
    return { totalCost, totalQty, totalValue, netPnl, netPnlPct };
  }, [selectedLots, marketPrice]);

  // ─── Helpers ───

  const fmt = formatNumber;
  const fmtQuote = (num) => formatQuote(num, activeSymbol);
  const fmtBase = (num) => formatBase(num, activeSymbol);

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
          <button onClick={dismissMessage}>&times;</button>
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
                        {fmt(s.net_qty_base, 8)}
                      </div>
                      <div>
                        <span className="label">Netto Kosten</span><br />
                        {fmtQuote(s.net_cost)}
                      </div>
                      <div>
                        <span className="label">Netto P&L</span><br />
                        {fmtQuote(s.net_pnl_quote)}
                      </div>
                      <div>
                        <span className="label">Marktwert</span><br />
                        {fmtQuote(s.net_value)}
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
                  <span className="summary-value">{fmtBase(manualPreview.totalQty)}</span>
                </div>
                <div className="summary-card">
                  <span className="summary-label">Gesamt Kosten</span>
                  <span className="summary-value">{fmtQuote(manualPreview.totalCost)}</span>
                </div>
                <div className={`summary-card ${manualPreview.netPnl >= 0 ? 'summary-profit' : 'summary-loss'}`}>
                  <span className="summary-label">Netto P&L</span>
                  <span className="summary-value">
                    {fmtQuote(manualPreview.netPnl)} ({manualPreview.netPnlPct >= 0 ? '+' : ''}{fmt(manualPreview.netPnlPct)}%)
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
                        <td>{fmtBase(lot.qty_base_open)}</td>
                        <td>{fmtQuote(lot.break_even)}</td>
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
        <PairingExistingTab
          onHighlightLots={onHighlightLots}
          showMessage={showMessage}
        />
      )}
    </div>
  );
};

export default PairingPanel;
