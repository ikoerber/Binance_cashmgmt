/**
 * LotsTable - Zeigt alle TradeLots mit Filtern und Binance-Sync
 *
 * Delegiert Daten-Fetching an useLotsData, Summary-KPIs an LotSummaryCards.
 */
import { useState, useMemo, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { syncLots, createOrderForLot, mergeLots } from '../api/client';
import PairingPanel from './PairingPanel';
import LotFilters from './LotFilters';
import OpenOrdersPanel from './OpenOrdersPanel';
import LotSummaryCards from './LotSummaryCards';
import useLotsData from '../hooks/useLotsData';
import useNotification from '../hooks/useNotification';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import { formatNumber, formatQuote, formatBase, formatDate, formatTime } from '../utils/formatters';
import './LotsTable.css';

const LotsTable = () => {
  const { userId } = useUser();
  const { symbol: activeSymbol, marketPrice } = useSymbol();
  const queryClient = useQueryClient();
  const { message: syncMessage, showMessage, dismissMessage } = useNotification(8000);

  // Pairing state
  const [selectedLotIds, setSelectedLotIds] = useState(new Set());
  const [pairingPanelOpen, setPairingPanelOpen] = useState(false);
  const [pairingActiveTab, setPairingActiveTab] = useState('suggestions');
  const [highlightedLotIds, setHighlightedLotIds] = useState(new Set());

  // Data hook
  const {
    filters,
    sortColumn, sortDirection, toggleSort,
    isLoading, error,
    lots, openOrders, openBuyOrders, openCostSum, totalOpenQty, filteredOpenQtySum,
    orderByLotId, mergeGroupByLotId, depotPnl,
  } = useLotsData();

  const toggleLotSelection = (lotId) => {
    setSelectedLotIds((prev) => {
      const next = new Set(prev);
      if (next.has(lotId)) {
        next.delete(lotId);
      } else {
        next.add(lotId);
        if (!pairingPanelOpen) {
          setPairingPanelOpen(true);
        }
        setPairingActiveTab('manual');
      }
      return next;
    });
  };

  const clearSelection = () => setSelectedLotIds(new Set());

  // Sync Mutation
  const syncMutation = useMutation({
    mutationFn: () => syncLots(userId, activeSymbol),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['lots'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      const report = data.sync_report;
      const fiatCount = (report.fiat_deposits || 0) + (report.fiat_withdrawals || 0);
      if (report.new_fills > 0 || fiatCount > 0) {
        const parts = [];
        if (report.new_fills > 0) {
          parts.push(`${report.new_fills} neue Fills, ${report.new_lots} Lots, ${report.allocations} Allocations`);
        }
        if (report.fiat_deposits > 0) {
          parts.push(`${report.fiat_deposits} Fiat-Einzahlung${report.fiat_deposits !== 1 ? 'en' : ''}`);
        }
        if (report.fiat_withdrawals > 0) {
          parts.push(`${report.fiat_withdrawals} Fiat-Auszahlung${report.fiat_withdrawals !== 1 ? 'en' : ''}`);
        }
        showMessage('success', parts.join(', '));
      } else {
        showMessage('info', 'Keine neuen Trades oder Fiat-Transaktionen auf Binance gefunden.');
      }
    },
    onError: (err) => showMessage('error', err.response?.data?.detail || err.message),
  });

  // Create Order Mutation
  const createOrderMutation = useMutation({
    mutationFn: ({ lotId }) => createOrderForLot(userId, lotId),
    onSuccess: (data, { lotId }) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['lots'] });
      showMessage(
        data.status === 'duplicate' ? 'info' : 'success',
        data.status === 'duplicate'
          ? 'Order existiert bereits (Idempotenz).'
          : `Sell Order erstellt für Lot ${lotId.slice(0, 8)}...`
      );
    },
    onError: (err) => showMessage('error', err.response?.data?.detail || err.message),
  });

  // Merge Mutation
  const mergeMutation = useMutation({
    mutationFn: ({ lotIds }) => mergeLots(userId, lotIds),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['lots'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['merge-groups'] });
      showMessage('success', `${data.merged_count} Lot${data.merged_count !== 1 ? 's' : ''} zusammengefasst`);
    },
    onError: (err) => showMessage('error', err.response?.data?.detail || err.message),
  });

  // Stale Selections bereinigen
  useEffect(() => {
    if (selectedLotIds.size === 0) return;
    const visibleIds = new Set(lots.map((lot) => lot.id));
    const stale = [...selectedLotIds].filter((id) => !visibleIds.has(id));
    if (stale.length > 0) {
      setSelectedLotIds((prev) => {
        const next = new Set(prev);
        stale.forEach((id) => next.delete(id));
        return next;
      });
    }
  }, [lots]);

  const selectAllVisible = () => {
    const openLotIds = lots
      .filter((lot) => lot.status !== 'CLOSED')
      .map((lot) => lot.id);
    setSelectedLotIds(new Set(openLotIds));
  };

  const selectedLots = useMemo(() => {
    return lots.filter((lot) => selectedLotIds.has(lot.id));
  }, [lots, selectedLotIds]);

  if (isLoading) return <div className="loading">Lade TradeLots...</div>;
  if (error) return <div className="error">Fehler: {error.message}</div>;

  const calculateUnrealizedPnl = (lot) => {
    const qtyOpen = parseFloat(lot.qty_base_open);
    const breakEven = parseFloat(lot.break_even);
    return (marketPrice * qtyOpen) - (breakEven * qtyOpen);
  };

  const calculateUnrealizedPnlPct = (lot) => {
    const breakEven = parseFloat(lot.break_even);
    return ((marketPrice / breakEven) - 1) * 100;
  };

  return (
    <div className="lots-table-container">
      {/* Header mit Sync-Button */}
      <div className="lots-header">
        <h2>TradeLots <span>({lots.length})</span></h2>
        <button
          className="btn-sync"
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
        >
          {syncMutation.isPending ? (
            <><span className="spinner" /> Synchronisiere...</>
          ) : (
            'Binance Sync'
          )}
        </button>
      </div>

      {/* Sync-Feedback */}
      {syncMessage && (
        <div className={`sync-message sync-${syncMessage.type}`}>
          {syncMessage.type === 'success' && '+ '}
          {syncMessage.type === 'error' && 'Fehler: '}
          {syncMessage.text}
          <button className="sync-message-close" onClick={dismissMessage}>&times;</button>
        </div>
      )}

      {/* Summary Cards (delegiert an LotSummaryCards) */}
      <LotSummaryCards
        openCostSum={openCostSum}
        filteredOpenQtySum={filteredOpenQtySum}
        totalOpenQty={totalOpenQty}
        depotPnl={depotPnl}
      />

      <OpenOrdersPanel openOrders={openOrders} openBuyOrders={openBuyOrders} />

      {/* Filter Bar */}
      <LotFilters
        statusFilter={filters.statusFilter} setStatusFilter={filters.setStatusFilter}
        fromDate={filters.fromDate} setFromDate={filters.setFromDate}
        toDate={filters.toDate} setToDate={filters.setToDate}
        orderFilter={filters.orderFilter} setOrderFilter={filters.setOrderFilter}
        showClosed={filters.showClosed} setShowClosed={filters.setShowClosed}
      />

      {/* Pairing Action Bar */}
      <div className="pairing-action-bar">
        <button
          className={`btn-pairing-toggle ${pairingPanelOpen ? 'active' : ''}`}
          onClick={() => setPairingPanelOpen(!pairingPanelOpen)}
        >
          {pairingPanelOpen ? 'Pairing schließen' : 'Pairing'}
          {selectedLotIds.size > 0 && (
            <span className="selection-badge">{selectedLotIds.size}</span>
          )}
        </button>
        {selectedLotIds.size > 0 && (
          <>
            <span className="selection-info">
              {selectedLotIds.size} Lot{selectedLotIds.size !== 1 ? 's' : ''} ausgewählt
            </span>
            <button className="btn-clear-selection" onClick={clearSelection}>
              Auswahl aufheben
            </button>
          </>
        )}
      </div>

      {/* Pairing Panel */}
      {pairingPanelOpen && (
        <PairingPanel
          selectedLots={selectedLots}
          onClearSelection={clearSelection}
          onToggleLot={toggleLotSelection}
          activeTab={pairingActiveTab}
          onTabChange={setPairingActiveTab}
          onHighlightLots={setHighlightedLotIds}
        />
      )}

      {lots.length === 0 ? (
        <div className="no-data">
          <p>Keine TradeLots vorhanden.</p>
          <p>Klicke oben auf <strong>Binance Sync</strong>, um Trades von Binance zu importieren.</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="lots-table">
            <thead>
              <tr>
                <th className="checkbox-col">
                  <input
                    type="checkbox"
                    checked={selectedLotIds.size > 0 && lots.filter(l => l.status !== 'CLOSED').every(l => selectedLotIds.has(l.id))}
                    onChange={(e) => e.target.checked ? selectAllVisible() : clearSelection()}
                    title="Alle auswählen"
                  />
                </th>
                <th>Order Nr.</th>
                <th className="sortable" onClick={() => toggleSort('date')}>
                  Datum
                  <span className={`sort-icon ${sortColumn === 'date' ? 'active' : ''}`}>
                    {sortColumn === 'date' ? (sortDirection === 'asc' ? ' \u25B2' : ' \u25BC') : ' \u21C5'}
                  </span>
                </th>
                <th>Uhrzeit</th>
                <th>Menge Initial</th>
                <th>Menge Offen</th>
                <th>Kosten</th>
                <th className="sortable" onClick={() => toggleSort('break_even')}>
                  Break-even
                  <span className={`sort-icon ${sortColumn === 'break_even' ? 'active' : ''}`}>
                    {sortColumn === 'break_even' ? (sortDirection === 'asc' ? ' \u25B2' : ' \u25BC') : ' \u21C5'}
                  </span>
                </th>
                <th>Sell Order</th>
                <th>Unrealisiert P&L</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot) => {
                const unrealizedPnl = calculateUnrealizedPnl(lot);
                const unrealizedPnlPct = calculateUnrealizedPnlPct(lot);
                const isProfitable = unrealizedPnl >= 0;

                return (
                  <tr key={lot.id} className={`${selectedLotIds.has(lot.id) ? 'lot-selected' : ''} ${highlightedLotIds.has(lot.id) ? 'lot-highlighted' : ''} ${mergeGroupByLotId[lot.id] ? 'lot-merge-group' : ''}`}>
                    <td className="checkbox-col">
                      {lot.status !== 'CLOSED' && (
                        <input
                          type="checkbox"
                          checked={selectedLotIds.has(lot.id)}
                          onChange={() => toggleLotSelection(lot.id)}
                        />
                      )}
                    </td>
                    <td className="order-id">
                      {lot.binance_order_id || (lot.import_source === 'trading_bots_csv' ? <span className="import-source-badge">Bot-Import</span> : '–')}
                      {mergeGroupByLotId[lot.id] && (
                        <button
                          className="btn-merge"
                          onClick={() => {
                            const group = mergeGroupByLotId[lot.id];
                            const lotIds = group.lots.map((l) => l.id);
                            if (
                              window.confirm(
                                `${lotIds.length} Lots der Order ${group.binance_order_id} zusammenfassen?\n` +
                                  `Gesamt: ${formatBase(group.total_qty_base, activeSymbol)}, ${formatQuote(group.total_cost_quote, activeSymbol)}`
                              )
                            ) {
                              mergeMutation.mutate({ lotIds });
                            }
                          }}
                          disabled={mergeMutation.isPending}
                          title="Partial Fills zusammenfassen"
                        >
                          Zusammenfassen
                        </button>
                      )}
                    </td>
                    <td className="date">{formatDate(lot.created_at)}</td>
                    <td className="time">{formatTime(lot.created_at)}</td>
                    <td>{formatBase(lot.qty_base_initial, activeSymbol)}</td>
                    <td>{formatBase(lot.qty_base_open, activeSymbol)}</td>
                    <td>{formatQuote(lot.cost_quote, activeSymbol)}</td>
                    <td>{formatQuote(lot.break_even, activeSymbol)}</td>
                    <td className="sell-order-cell">
                      {orderByLotId[lot.id] ? (
                        <span className={`order-indicator ${parseFloat(orderByLotId[lot.id].price) <= marketPrice ? 'order-below-market' : ''}`}>
                          <span className={`order-status-dot ${parseFloat(orderByLotId[lot.id].price) <= marketPrice ? 'warning' : 'open'}`} />
                          {formatQuote(orderByLotId[lot.id].price, activeSymbol)}
                          {parseFloat(orderByLotId[lot.id].price) <= marketPrice && (
                            <span className="order-warning-badge" title={`Sell-Preis liegt unter dem Marktpreis (${formatQuote(marketPrice, activeSymbol)})`}>
                              Unter Markt
                            </span>
                          )}
                        </span>
                      ) : lot.status !== 'CLOSED' ? (
                        <button
                          className="btn-create-order"
                          onClick={() => {
                            if (window.confirm(`Sell Order für Lot ${lot.binance_order_id || lot.id.slice(0, 8)} erstellen?`)) {
                              createOrderMutation.mutate({ lotId: lot.id });
                            }
                          }}
                          disabled={createOrderMutation.isPending}
                          title="Sell Order erstellen"
                        >
                          {createOrderMutation.isPending && createOrderMutation.variables?.lotId === lot.id
                            ? '...'
                            : '+ Order'}
                        </button>
                      ) : '-'}
                    </td>
                    <td className={isProfitable ? 'profit' : 'loss'}>
                      <div className="pnl-cell">
                        <span className="pnl-amount">{formatQuote(unrealizedPnl, activeSymbol)}</span>
                        <span className="pnl-pct">{unrealizedPnlPct >= 0 ? '+' : ''}{formatNumber(unrealizedPnlPct, 2)}%</span>
                      </div>
                    </td>
                    <td>
                      <span className={`status-badge ${lot.status.toLowerCase()}`}>
                        {lot.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default LotsTable;
