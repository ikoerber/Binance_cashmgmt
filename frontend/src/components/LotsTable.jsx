/**
 * LotsTable - Zeigt alle TradeLots mit Filtern und Binance-Sync
 */
import { useState, useMemo, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getLots, getOrdersForUser, syncLots, createOrderForLot, listPairings, getPortfolio, getMergeGroups, mergeLots } from '../api/client';
import PairingPanel from './PairingPanel';
import LotFilters from './LotFilters';
import OpenOrdersPanel from './OpenOrdersPanel';
import { formatNumber, formatEUR, formatBTC, formatDate, formatTime } from '../utils/formatters';
import './LotsTable.css';

// Preis auf 50 EUR runden, damit der queryKey nicht bei jedem Tick wechselt
const roundPrice = (p) => Math.round(p / 50) * 50;

const LotsTable = ({ userId = 'user_123', marketPrice = 50000 }) => {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState(null);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [orderFilter, setOrderFilter] = useState('');
  const [showClosed, setShowClosed] = useState(false);
  const [sortColumn, setSortColumn] = useState(null); // 'date' | 'break_even'
  const [sortDirection, setSortDirection] = useState('asc');
  const [syncMessage, setSyncMessage] = useState(null);

  // Pairing state
  const [selectedLotIds, setSelectedLotIds] = useState(new Set());
  const [pairingPanelOpen, setPairingPanelOpen] = useState(false);
  const [pairingActiveTab, setPairingActiveTab] = useState('suggestions');
  const [highlightedLotIds, setHighlightedLotIds] = useState(new Set());

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

  const toggleSort = (column) => {
    if (sortColumn === column) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  // Sync Mutation
  const syncMutation = useMutation({
    mutationFn: () => syncLots(userId),
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
        setSyncMessage({
          type: 'success',
          text: parts.join(', '),
        });
      } else {
        setSyncMessage({
          type: 'info',
          text: 'Keine neuen Trades oder Fiat-Transaktionen auf Binance gefunden.',
        });
      }
      setTimeout(() => setSyncMessage(null), 8000);
    },
    onError: (error) => {
      setSyncMessage({
        type: 'error',
        text: error.response?.data?.detail || error.message,
      });
      setTimeout(() => setSyncMessage(null), 8000);
    },
  });

  // Create Order Mutation (Einzel-Lot)
  const createOrderMutation = useMutation({
    mutationFn: ({ lotId }) => createOrderForLot(userId, lotId),
    onSuccess: (data, { lotId }) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['lots'] });
      if (data.status === 'duplicate') {
        setSyncMessage({ type: 'info', text: 'Order existiert bereits (Idempotenz).' });
      } else {
        setSyncMessage({ type: 'success', text: `Sell Order erstellt für Lot ${lotId.slice(0, 8)}...` });
      }
      setTimeout(() => setSyncMessage(null), 8000);
    },
    onError: (error) => {
      setSyncMessage({ type: 'error', text: error.response?.data?.detail || error.message });
      setTimeout(() => setSyncMessage(null), 8000);
    },
  });

  // Merge Groups Query
  const { data: mergeGroupsData } = useQuery({
    queryKey: ['merge-groups', userId],
    queryFn: () => getMergeGroups(userId),
  });

  // Merge-Lookup: lotId -> mergeGroup
  const mergeGroupByLotId = useMemo(() => {
    const map = {};
    for (const group of mergeGroupsData?.groups || []) {
      for (const lot of group.lots) {
        map[lot.id] = group;
      }
    }
    return map;
  }, [mergeGroupsData]);

  // Merge Mutation
  const mergeMutation = useMutation({
    mutationFn: ({ lotIds }) => mergeLots(userId, lotIds),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['lots'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['merge-groups'] });
      setSyncMessage({
        type: 'success',
        text: `${data.merged_count} Lot${data.merged_count !== 1 ? 's' : ''} zusammengefasst`,
      });
      setTimeout(() => setSyncMessage(null), 8000);
    },
    onError: (error) => {
      setSyncMessage({
        type: 'error',
        text: error.response?.data?.detail || error.message,
      });
      setTimeout(() => setSyncMessage(null), 8000);
    },
  });

  // Lots werden per WebSocket order_update Event invalidiert (kein Polling noetig)
  const { data: lotsData, isLoading, error } = useQuery({
    queryKey: ['lots', userId, statusFilter, fromDate, toDate],
    queryFn: () => getLots(
      userId,
      statusFilter,
      1000,
      0,
      fromDate || null,
      toDate ? `${toDate}T23:59:59` : null
    ),
  });

  // Client-side Filter + Sortierung (Hooks müssen vor Early Returns stehen)
  const lots = useMemo(() => {
    const allLots = lotsData?.lots || [];
    let filtered = orderFilter
      ? allLots.filter((lot) =>
          lot.binance_order_id &&
          lot.binance_order_id.toString().includes(orderFilter)
        )
      : allLots;
    if (!showClosed) {
      filtered = filtered.filter((lot) => lot.status !== 'CLOSED');
    }
    if (!sortColumn) return filtered;
    const sorted = [...filtered].sort((a, b) => {
      if (sortColumn === 'date') {
        return new Date(a.created_at) - new Date(b.created_at);
      }
      if (sortColumn === 'break_even') {
        return parseFloat(a.break_even) - parseFloat(b.break_even);
      }
      return 0;
    });
    return sortDirection === 'desc' ? sorted.reverse() : sorted;
  }, [lotsData, orderFilter, showClosed, sortColumn, sortDirection]);

  // Stale Selections bereinigen: IDs entfernen die nicht mehr in den sichtbaren Lots sind
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

  // Summe Kosten offener Positionen (OPEN + PARTIAL_CLOSED)
  const openCostSum = useMemo(() => {
    const allLots = lotsData?.lots || [];
    return allLots
      .filter((lot) => lot.status === 'OPEN' || lot.status === 'PARTIAL_CLOSED')
      .reduce((sum, lot) => sum + parseFloat(lot.cost_eur), 0);
  }, [lotsData]);

  // Gesamte offene BTC-Menge (alle Lots, nicht nur gefilterte) für Erholungspreis
  const totalOpenQty = useMemo(() => {
    const allLots = lotsData?.lots || [];
    return allLots
      .filter((lot) => lot.status === 'OPEN' || lot.status === 'PARTIAL_CLOSED')
      .reduce((sum, lot) => sum + parseFloat(lot.qty_btc_open), 0);
  }, [lotsData]);

  // Summe Menge Offen der gefilterten Liste
  const filteredOpenQtySum = useMemo(() => {
    return lots.reduce((sum, lot) => sum + parseFloat(lot.qty_btc_open), 0);
  }, [lots]);

  // Selected lots for pairing
  const selectedLots = useMemo(() => {
    return lots.filter((lot) => selectedLotIds.has(lot.id));
  }, [lots, selectedLotIds]);

  // Orders werden per WebSocket order_update Event invalidiert (kein Polling noetig)
  const { data: ordersData } = useQuery({
    queryKey: ['orders', userId, 'open'],
    queryFn: () => getOrdersForUser(userId, 'OPEN'),
  });

  const openOrders = useMemo(() => ordersData?.orders || [], [ordersData]);

  // Pairings laden (cached via PairingPanel) - fuer Pairing→Lot Zuordnung
  const { data: pairingsData } = useQuery({
    queryKey: ['pairings', userId, null],
    queryFn: () => listPairings(userId),
  });

  // Portfolio wird per WebSocket balance_update Event invalidiert
  // stablePrice im queryKey: Refetch nur bei >= 50 EUR Aenderung
  const stablePrice = roundPrice(marketPrice);
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio', userId, stablePrice],
    queryFn: () => getPortfolio(userId, marketPrice),
    enabled: !!marketPrice,
  });

  const depotPnl = portfolio
    ? (parseFloat(portfolio.market_value_eur) + parseFloat(portfolio.eur_available))
      - parseFloat(portfolio.external_net_eur)
    : null;

  // Lookup: lotId -> offene Order (direkt via linked_lot_id ODER via Pairing)
  const orderByLotId = useMemo(() => {
    const map = {};
    // 1. Direkte Lot-Verknüpfung
    for (const order of openOrders) {
      if (order.linked_lot_id) {
        map[order.linked_lot_id] = order;
      }
    }
    // 2. Pairing-Verknüpfung: Order → Pairing → Lots
    const pairings = pairingsData?.pairings || [];
    for (const order of openOrders) {
      if (order.linked_pairing_id && !order.linked_lot_id) {
        const pairing = pairings.find((p) => p.id === order.linked_pairing_id);
        if (pairing) {
          for (const item of pairing.items) {
            if (!map[item.lot_id]) {
              map[item.lot_id] = order;
            }
          }
        }
      }
    }
    return map;
  }, [openOrders, pairingsData]);

  const FEE_RATE = 0.001; // 0.1% Binance Spot Fee

  // Portfolio-Erholungspreis: alle offenen Lots tragen proportional (nach qty) bei
  // WICHTIG: useMemo muss VOR Early Returns stehen (Rules of Hooks)
  const recoveryPrice = useMemo(() => {
    if (depotPnl === null || depotPnl >= 0 || totalOpenQty <= 0) return null;
    const deficit = Math.abs(depotPnl);
    return (totalOpenQty * marketPrice + deficit) / (totalOpenQty * (1 - FEE_RATE));
  }, [depotPnl, totalOpenQty, marketPrice]);

  if (isLoading) return <div className="loading">Lade TradeLots...</div>;
  if (error) return <div className="error">Fehler: {error.message}</div>;

  const calculateUnrealizedPnl = (lot) => {
    const qtyOpen = parseFloat(lot.qty_btc_open);
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
          <button className="sync-message-close" onClick={() => setSyncMessage(null)}>&times;</button>
        </div>
      )}

      {/* Summary Cards */}
      <div className="lots-summary">
        <div className="summary-card">
          <span className="summary-label">Kosten offene Positionen</span>
          <span className="summary-value">{formatEUR(openCostSum)}</span>
        </div>
        <div className="summary-card">
          <span className="summary-label">Menge Offen (gefiltert)</span>
          <span className="summary-value">{formatBTC(filteredOpenQtySum)}</span>
        </div>
        {recoveryPrice !== null && (
          <div className="summary-card recovery-card">
            <span className="summary-label">Erholungspreis</span>
            <span className="summary-value recovery-value">{formatEUR(recoveryPrice)}</span>
            <span className="summary-sub">+{formatNumber(((recoveryPrice / marketPrice) - 1) * 100, 1)}% über Markt | Deficit: {formatEUR(Math.abs(depotPnl))}</span>
          </div>
        )}
      </div>

      <OpenOrdersPanel openOrders={openOrders} marketPrice={marketPrice} />

      {/* Filter Bar */}
      <LotFilters
        statusFilter={statusFilter} setStatusFilter={setStatusFilter}
        fromDate={fromDate} setFromDate={setFromDate}
        toDate={toDate} setToDate={setToDate}
        orderFilter={orderFilter} setOrderFilter={setOrderFilter}
        showClosed={showClosed} setShowClosed={setShowClosed}
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
          userId={userId}
          marketPrice={marketPrice}
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
                                  `Gesamt: ${formatBTC(group.total_qty_btc)} BTC, ${formatEUR(group.total_cost_eur)}`
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
                    <td>{formatBTC(lot.qty_btc_initial)}</td>
                    <td>{formatBTC(lot.qty_btc_open)}</td>
                    <td>{formatEUR(lot.cost_eur)}</td>
                    <td>{formatEUR(lot.break_even)}</td>
                    <td className="sell-order-cell">
                      {orderByLotId[lot.id] ? (
                        <span className={`order-indicator ${parseFloat(orderByLotId[lot.id].price) <= marketPrice ? 'order-below-market' : ''}`}>
                          <span className={`order-status-dot ${parseFloat(orderByLotId[lot.id].price) <= marketPrice ? 'warning' : 'open'}`} />
                          {formatEUR(orderByLotId[lot.id].price)}
                          {parseFloat(orderByLotId[lot.id].price) <= marketPrice && (
                            <span className="order-warning-badge" title={`Sell-Preis liegt unter dem Marktpreis (${formatEUR(marketPrice)})`}>
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
                        <span className="pnl-amount">{formatEUR(unrealizedPnl)}</span>
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
