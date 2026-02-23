/**
 * useLotsData - Custom Hook fuer Lots-Daten, Filter und Sortierung
 *
 * Extrahiert aus LotsTable: Queries, Filter-State, Sort-State, berechnete Werte.
 * Filter-State wird in URL Search Params persistiert (Phase 4):
 * - Symbol-Wechsel startet sauber (ohne Filter)
 * - Browser Back/Forward behaelt Filter bei
 */
import { useMemo, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getLots, getOrdersForUser, listPairings, getPortfolio, getMergeGroups } from '../api/client';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';

const roundPrice = (p) => Math.round(p / 50) * 50;

export default function useLotsData() {
  const { userId } = useUser();
  const { symbol: activeSymbol, marketPrice } = useSymbol();

  // Filter state via URL Search Params
  const [searchParams, setSearchParams] = useSearchParams();

  const statusFilter = searchParams.get('status') || null;
  const fromDate = searchParams.get('from') || '';
  const toDate = searchParams.get('to') || '';
  const orderFilter = searchParams.get('order') || '';
  const showClosed = searchParams.get('closed') === '1';
  const sortColumn = searchParams.get('sort') || null;
  const sortDirection = searchParams.get('dir') || 'asc';

  // Helper: Update einzelnen Search Param (entfernt leere Werte)
  const setParam = useCallback((key, value) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (value === null || value === '' || value === undefined) {
        next.delete(key);
      } else {
        next.set(key, value);
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const setStatusFilter = (v) => setParam('status', v);
  const setFromDate = (v) => setParam('from', v);
  const setToDate = (v) => setParam('to', v);
  const setOrderFilter = (v) => setParam('order', v);
  const setShowClosed = (v) => setParam('closed', v ? '1' : null);

  const toggleSort = (column) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (sortColumn === column) {
        next.set('dir', sortDirection === 'asc' ? 'desc' : 'asc');
      } else {
        next.set('sort', column);
        next.set('dir', 'asc');
      }
      return next;
    }, { replace: true });
  };

  // ─── Queries ───

  const { data: lotsData, isLoading, error } = useQuery({
    queryKey: ['lots', activeSymbol, userId, statusFilter, fromDate, toDate],
    queryFn: () => getLots(userId, statusFilter, 1000, 0, fromDate || null, toDate ? `${toDate}T23:59:59` : null, activeSymbol),
  });

  const { data: ordersData } = useQuery({
    queryKey: ['orders', activeSymbol, userId, 'open'],
    queryFn: () => getOrdersForUser(userId, 'OPEN', activeSymbol),
  });

  const { data: pairingsData } = useQuery({
    queryKey: ['pairings', activeSymbol, userId, null],
    queryFn: () => listPairings(userId, null, activeSymbol),
  });

  const stablePrice = roundPrice(marketPrice);
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio', activeSymbol, userId, stablePrice],
    queryFn: () => getPortfolio(userId, marketPrice, activeSymbol),
    enabled: !!marketPrice,
  });

  const { data: mergeGroupsData } = useQuery({
    queryKey: ['merge-groups', activeSymbol, userId],
    queryFn: () => getMergeGroups(userId, activeSymbol),
  });

  // ─── Computed Values ───

  const lots = useMemo(() => {
    const allLots = lotsData?.lots || [];
    let filtered = orderFilter
      ? allLots.filter((lot) => lot.binance_order_id && lot.binance_order_id.toString().includes(orderFilter))
      : allLots;
    if (!showClosed) {
      filtered = filtered.filter((lot) => lot.status !== 'CLOSED');
    }
    if (!sortColumn) return filtered;
    const sorted = [...filtered].sort((a, b) => {
      if (sortColumn === 'date') return new Date(a.created_at) - new Date(b.created_at);
      if (sortColumn === 'break_even') return parseFloat(a.break_even) - parseFloat(b.break_even);
      return 0;
    });
    return sortDirection === 'desc' ? sorted.reverse() : sorted;
  }, [lotsData, orderFilter, showClosed, sortColumn, sortDirection]);

  const openOrders = useMemo(() => (ordersData?.orders || []).filter((o) => o.side === 'SELL'), [ordersData]);
  const openBuyOrders = useMemo(() => (ordersData?.orders || []).filter((o) => o.side === 'BUY'), [ordersData]);

  const openCostSum = useMemo(() => {
    const allLots = lotsData?.lots || [];
    return allLots
      .filter((lot) => lot.status === 'OPEN' || lot.status === 'PARTIAL_CLOSED')
      .reduce((sum, lot) => sum + parseFloat(lot.cost_quote), 0);
  }, [lotsData]);

  const totalOpenQty = useMemo(() => {
    const allLots = lotsData?.lots || [];
    return allLots
      .filter((lot) => lot.status === 'OPEN' || lot.status === 'PARTIAL_CLOSED')
      .reduce((sum, lot) => sum + parseFloat(lot.qty_base_open), 0);
  }, [lotsData]);

  const filteredOpenQtySum = useMemo(() => {
    return lots.reduce((sum, lot) => sum + parseFloat(lot.qty_base_open), 0);
  }, [lots]);

  const orderByLotId = useMemo(() => {
    const map = {};
    for (const order of openOrders) {
      if (order.linked_lot_id) map[order.linked_lot_id] = order;
    }
    const pairings = pairingsData?.pairings || [];
    for (const order of openOrders) {
      if (order.linked_pairing_id && !order.linked_lot_id) {
        const pairing = pairings.find((p) => p.id === order.linked_pairing_id);
        if (pairing) {
          for (const item of pairing.items) {
            if (!map[item.lot_id]) map[item.lot_id] = order;
          }
        }
      }
    }
    return map;
  }, [openOrders, pairingsData]);

  const mergeGroupByLotId = useMemo(() => {
    const map = {};
    for (const group of mergeGroupsData?.groups || []) {
      for (const lot of group.lots) {
        map[lot.id] = group;
      }
    }
    return map;
  }, [mergeGroupsData]);

  // Per-Symbol Depot P&L (realisiert + unrealisiert)
  const depotPnl = portfolio?.depot_pnl_quote != null
    ? parseFloat(portfolio.depot_pnl_quote)
    : null;

  return {
    // Filter state + setters
    filters: {
      statusFilter, setStatusFilter,
      fromDate, setFromDate,
      toDate, setToDate,
      orderFilter, setOrderFilter,
      showClosed, setShowClosed,
    },
    // Sort
    sortColumn, sortDirection, toggleSort,
    // Query state
    isLoading, error,
    // Computed data
    lots, openOrders, openBuyOrders, openCostSum, totalOpenQty, filteredOpenQtySum,
    orderByLotId, mergeGroupByLotId, depotPnl,
  };
}
