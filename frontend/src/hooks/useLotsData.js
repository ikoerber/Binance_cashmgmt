/**
 * useLotsData - Custom Hook fuer Lots-Daten, Filter und Sortierung
 *
 * Extrahiert aus LotsTable: Queries, Filter-State, Sort-State, berechnete Werte.
 */
import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getLots, getOrdersForUser, listPairings, getPortfolio, getMergeGroups } from '../api/client';
import { useAppState } from '../contexts/AppStateContext';

const roundPrice = (p) => Math.round(p / 50) * 50;

export default function useLotsData() {
  const { userId, marketPrice } = useAppState();

  // Filter state
  const [statusFilter, setStatusFilter] = useState(null);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [orderFilter, setOrderFilter] = useState('');
  const [showClosed, setShowClosed] = useState(false);

  // Sort state
  const [sortColumn, setSortColumn] = useState(null);
  const [sortDirection, setSortDirection] = useState('asc');

  const toggleSort = (column) => {
    if (sortColumn === column) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  // ─── Queries ───

  const { data: lotsData, isLoading, error } = useQuery({
    queryKey: ['lots', userId, statusFilter, fromDate, toDate],
    queryFn: () => getLots(userId, statusFilter, 1000, 0, fromDate || null, toDate ? `${toDate}T23:59:59` : null),
  });

  const { data: ordersData } = useQuery({
    queryKey: ['orders', userId, 'open'],
    queryFn: () => getOrdersForUser(userId, 'OPEN'),
  });

  const { data: pairingsData } = useQuery({
    queryKey: ['pairings', userId, null],
    queryFn: () => listPairings(userId),
  });

  const stablePrice = roundPrice(marketPrice);
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio', userId, stablePrice],
    queryFn: () => getPortfolio(userId, marketPrice),
    enabled: !!marketPrice,
  });

  const { data: mergeGroupsData } = useQuery({
    queryKey: ['merge-groups', userId],
    queryFn: () => getMergeGroups(userId),
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

  const openOrders = useMemo(() => ordersData?.orders || [], [ordersData]);

  const openCostSum = useMemo(() => {
    const allLots = lotsData?.lots || [];
    return allLots
      .filter((lot) => lot.status === 'OPEN' || lot.status === 'PARTIAL_CLOSED')
      .reduce((sum, lot) => sum + parseFloat(lot.cost_eur), 0);
  }, [lotsData]);

  const totalOpenQty = useMemo(() => {
    const allLots = lotsData?.lots || [];
    return allLots
      .filter((lot) => lot.status === 'OPEN' || lot.status === 'PARTIAL_CLOSED')
      .reduce((sum, lot) => sum + parseFloat(lot.qty_btc_open), 0);
  }, [lotsData]);

  const filteredOpenQtySum = useMemo(() => {
    return lots.reduce((sum, lot) => sum + parseFloat(lot.qty_btc_open), 0);
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

  const depotPnl = portfolio
    ? (parseFloat(portfolio.market_value_eur) + parseFloat(portfolio.eur_available)) - parseFloat(portfolio.external_net_eur)
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
    lots, openOrders, openCostSum, totalOpenQty, filteredOpenQtySum,
    orderByLotId, mergeGroupByLotId, depotPnl,
  };
}
