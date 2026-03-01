/**
 * API Client für Backend
 */
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8100';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': import.meta.env.VITE_API_KEY || '',
  },
});

// Portfolio API
export const getPortfolio = async (userId, marketPrice, symbol = 'BTCEUR') => {
  const response = await apiClient.get(`/api/portfolio/${userId}`, {
    params: { market_price: marketPrice, symbol },
  });
  return response.data;
};

export const getDailyPerformance = async (userId, marketPrice, symbol = 'BTCEUR') => {
  const response = await apiClient.get(`/api/portfolio/${userId}/daily`, {
    params: { market_price: marketPrice, symbol },
  });
  return response.data;
};

export const getBnbFees = async (userId) => {
  const response = await apiClient.get(`/api/portfolio/${userId}/bnb-fees`);
  return response.data;
};

// Lots API
export const getLots = async (userId, status = null, limit = 100, offset = 0, fromDate = null, toDate = null, symbol = null) => {
  const response = await apiClient.get(`/api/lots/${userId}`, {
    params: { status, limit, offset, from_date: fromDate, to_date: toDate, symbol },
  });
  return response.data;
};

export const getLotDetail = async (userId, lotId) => {
  const response = await apiClient.get(`/api/lots/${userId}/${lotId}`);
  return response.data;
};

// Lot Merge API
export const getMergeGroups = async (userId, symbol = null) => {
  const response = await apiClient.get(`/api/lots/${userId}/merge-groups`, {
    params: { symbol },
  });
  return response.data;
};

export const mergeLots = async (userId, lotIds) => {
  const response = await apiClient.post(`/api/lots/${userId}/merge`, lotIds);
  return response.data;
};

// Orders API
export const getOrdersForUser = async (userId, status = null, symbol = null) => {
  const response = await apiClient.get(`/api/orders/${userId}/list`, {
    params: { status, symbol },
  });
  return response.data;
};

export const getBinanceOpenOrders = async (userId, symbol = 'BTCEUR') => {
  const response = await apiClient.get(`/api/orders/${userId}/open`, {
    params: { symbol },
  });
  return response.data;
};

export const syncOrderStatuses = async (userId) => {
  const response = await apiClient.post(`/api/orders/${userId}/sync-status`);
  return response.data;
};

export const importExternalOrders = async (userId, symbol = 'BTCEUR') => {
  const response = await apiClient.post(`/api/orders/${userId}/import`, null, {
    params: { symbol },
  });
  return response.data;
};

export const createOrderForLot = async (userId, lotId, targetMarginPct = 0.05, feeBufferPct = 0.002) => {
  const response = await apiClient.post(`/api/orders/${userId}/lot/${lotId}/create`, null, {
    params: { target_margin_pct: targetMarginPct, fee_buffer_pct: feeBufferPct },
  });
  return response.data;
};

// Sync API
export const syncLots = async (userId, symbol = 'BTCEUR', startTime = null) => {
  const response = await apiClient.post(`/api/lots/${userId}/sync`, null, {
    params: { symbol, start_time: startTime },
  });
  return response.data;
};

// Pairing API
export const getPairingSuggestions = async (userId, marketPrice, thresholdPct = 0.05, symbol = 'BTCEUR') => {
  const params = { market_price: marketPrice, threshold_pct: thresholdPct, symbol };
  const response = await apiClient.get(`/api/pairing/${userId}/suggestions`, { params });
  return response.data;
};

export const simulatePairing = async (userId, pairingId, marketPrice, feePct = 0.001, feeBufferPct = 0.002, customSellPrice = null) => {
  const params = { market_price: marketPrice, fee_pct: feePct, fee_buffer_pct: feeBufferPct };
  if (customSellPrice !== null) params.custom_sell_price = customSellPrice;
  const response = await apiClient.get(`/api/pairing/${userId}/simulate/${pairingId}`, { params });
  return response.data;
};

export const createPairing = async (userId, items, thresholdPct, symbol = 'BTCEUR') => {
  const body = { items, threshold_pct: thresholdPct, symbol };
  const response = await apiClient.post(`/api/pairing/${userId}/create`, body);
  return response.data;
};

export const listPairings = async (userId, status = null, symbol = null) => {
  const response = await apiClient.get(`/api/pairing/${userId}/list`, {
    params: { status, symbol },
  });
  return response.data;
};

export const lockPairing = async (userId, pairingId) => {
  const response = await apiClient.post(`/api/pairing/${userId}/${pairingId}/lock`);
  return response.data;
};

export const unlockPairing = async (userId, pairingId) => {
  const response = await apiClient.post(`/api/pairing/${userId}/${pairingId}/unlock`);
  return response.data;
};

export const executePairing = async (userId, pairingId, marketPrice, feeBufferPct = 0.002, customSellPrice = null) => {
  const params = { market_price: marketPrice, fee_buffer_pct: feeBufferPct };
  if (customSellPrice !== null) params.custom_sell_price = customSellPrice;
  const response = await apiClient.post(`/api/pairing/${userId}/${pairingId}/execute`, null, { params });
  return response.data;
};

export const deletePairing = async (userId, pairingId) => {
  const response = await apiClient.delete(`/api/pairing/${userId}/${pairingId}`);
  return response.data;
};

// Reconciliation API
export const runFullReconciliation = async (userId, symbol = 'BTCEUR') => {
  const response = await apiClient.post(`/api/reconciliation/${userId}/run`, null, {
    params: { symbol },
  });
  return response.data;
};

export const reconcileOrders = async (userId, symbol = 'BTCEUR') => {
  const response = await apiClient.post(`/api/reconciliation/${userId}/orders`, null, {
    params: { symbol },
  });
  return response.data;
};

export const reconcileBalances = async (userId, symbol = 'BTCEUR') => {
  const response = await apiClient.post(`/api/reconciliation/${userId}/balances`, null, {
    params: { symbol },
  });
  return response.data;
};

export const reconcileFills = async (userId, symbol = 'BTCEUR', startTime = null) => {
  const response = await apiClient.post(`/api/reconciliation/${userId}/fills`, null, {
    params: { symbol, start_time: startTime },
  });
  return response.data;
};

// Settings API
export const getSettings = async (userId) => {
  const response = await apiClient.get(`/api/settings/${userId}`);
  return response.data;
};

export const updateSettings = async (userId, settings) => {
  const response = await apiClient.put(`/api/settings/${userId}`, settings);
  return response.data;
};

// Combined Score API
export const getCombinedScore = async (userId, interval = '15', symbol = 'BTCEUR') => {
  const response = await apiClient.get(`/api/combined/${userId}/score`, {
    params: { interval, symbol },
  });
  return response.data;
};

// Orderblock API
export const analyzeOrderblocks = async (userId, { symbol = 'BTCEUR', interval, months = 6, config } = {}) => {
  const response = await apiClient.post(`/api/orderblock/${userId}/analyze`, {
    symbol,
    interval,
    months,
    config,
  });
  return response.data;
};

export const getOrderblockZones = async (userId, { symbol = 'BTCEUR', interval = '4h', state } = {}) => {
  const response = await apiClient.get(`/api/orderblock/${userId}/zones`, {
    params: { symbol, interval, state },
  });
  return response.data;
};

export const deleteOrderblockZones = async (userId, { symbol = 'BTCEUR', interval = '4h' } = {}) => {
  const response = await apiClient.delete(`/api/orderblock/${userId}/zones`, {
    params: { symbol, interval },
  });
  return response.data;
};

export const getOrderblockBacktestRuns = async (userId, symbol = null) => {
  const response = await apiClient.get(`/api/orderblock/${userId}/backtest/runs`, {
    params: { symbol },
  });
  return response.data;
};

export const getOrderblockCandles = async (userId, { symbol = 'BTCEUR', interval = '4h', zoneId, startTime, endTime, contextCandles = 80 } = {}) => {
  const response = await apiClient.get(`/api/orderblock/${userId}/candles`, {
    params: { symbol, interval, zone_id: zoneId, start_time: startTime, end_time: endTime, context_candles: contextCandles },
  });
  return response.data;
};

// Alerts API
export const getAlerts = async (userId, includeAcknowledged = false) => {
  const response = await apiClient.get(`/api/alerts/${userId}`, {
    params: { include_acknowledged: includeAcknowledged },
  });
  return response.data;
};

export const acknowledgeAlert = async (alertId, userId) => {
  const response = await apiClient.patch(`/api/alerts/${userId}/${alertId}/acknowledge`);
  return response.data;
};

export const acknowledgeAllAlerts = async (userId) => {
  const response = await apiClient.post(`/api/alerts/${userId}/acknowledge-all`);
  return response.data;
};

// Reconciliation History API
export const getReconciliationHistory = async (userId, limit = 20, offset = 0) => {
  const response = await apiClient.get(`/api/reconciliation/${userId}/history`, {
    params: { limit, offset },
  });
  return response.data;
};

export const getReconciliationRunDetail = async (userId, runId) => {
  const response = await apiClient.get(`/api/reconciliation/${userId}/history/${runId}`);
  return response.data;
};

// Backtest API
export const runBacktest = async (userId, { symbol = 'BTCEUR', months = 12, initial_capital = '10000', fee_rate = '0.001', slippage_pct = '0.0005', position_fraction = '0.10', entry_threshold, atr_multiplier } = {}) => {
  const body = { symbol, months, initial_capital, fee_rate, slippage_pct, position_fraction };
  if (entry_threshold) body.entry_threshold = entry_threshold;
  if (atr_multiplier) body.atr_multiplier = atr_multiplier;
  const response = await apiClient.post(`/api/backtest/${userId}/run`, body);
  return response.data;
};

export const getBacktestRuns = async (userId, symbol = null) => {
  const params = {};
  if (symbol) params.symbol = symbol;
  const response = await apiClient.get(`/api/backtest/${userId}/runs`, { params });
  return response.data;
};

export const getBacktestRunDetail = async (userId, runId) => {
  const response = await apiClient.get(`/api/backtest/${userId}/runs/${runId}`);
  return response.data;
};

export const cancelBacktest = async (userId, runId) => {
  const response = await apiClient.post(`/api/backtest/${userId}/cancel/${runId}`);
  return response.data;
};

export const runBacktestSweep = async (userId, { symbol = 'BTCEUR', months = 12, initial_capital = '10000', fee_rate, slippage_pct, position_fraction, sweep } = {}) => {
  const body = { symbol, months, initial_capital, sweep };
  if (fee_rate) body.fee_rate = fee_rate;
  if (slippage_pct) body.slippage_pct = slippage_pct;
  if (position_fraction) body.position_fraction = position_fraction;
  const response = await apiClient.post(`/api/backtest/${userId}/sweep`, body);
  return response.data;
};

export const getBacktestSweepDetail = async (userId, sweepId) => {
  const response = await apiClient.get(`/api/backtest/${userId}/sweep/${sweepId}`);
  return response.data;
};

export const getBacktestSweepCsvUrl = (userId, sweepId) => {
  const base = API_BASE_URL;
  return `${base}/api/backtest/${userId}/sweep/${sweepId}/csv`;
};

// Alpha Score API
export const getAlphaScore = async (userId, symbol = 'XRPBTC') => {
  const response = await apiClient.get(`/api/alpha-score/${userId}/score`, {
    params: { symbol },
  });
  return response.data;
};

export const getTrailingStops = async (userId) => {
  const response = await apiClient.get(`/api/alpha-score/${userId}/trailing-stops`);
  return response.data;
};

// Dry-Run API
export const getDryRunStatus = async (userId) => {
  const response = await apiClient.get(`/api/dry-run/${userId}/status`);
  return response.data;
};

export const toggleDryRun = async (userId) => {
  const response = await apiClient.post(`/api/dry-run/${userId}/toggle`);
  return response.data;
};

export const getDryRunDecisions = async (userId, { fromDate, toDate, action, symbol, limit = 50, offset = 0 } = {}) => {
  const response = await apiClient.get(`/api/dry-run/${userId}/decisions`, {
    params: { from_date: fromDate, to_date: toDate, action, symbol, limit, offset },
  });
  return response.data;
};

export const getDryRunDecisionDetail = async (userId, decisionId) => {
  const response = await apiClient.get(`/api/dry-run/${userId}/decisions/${decisionId}`);
  return response.data;
};

export const resetDryRunPortfolio = async (userId) => {
  const response = await apiClient.post(`/api/dry-run/${userId}/reset`);
  return response.data;
};

export const getDryRunPortfolio = async (userId) => {
  const response = await apiClient.get(`/api/dry-run/${userId}/portfolio`);
  return response.data;
};

// Server IP API
export const getServerIp = async () => {
  const response = await apiClient.get('/api/server-ip');
  return response.data;
};

// Balances API
export const getActiveSymbols = async (userId) => {
  const response = await apiClient.get(`/api/balances/${userId}/active-symbols`);
  return response.data;
};

// Health API
export const getHealth = async (userId) => {
  const response = await apiClient.get(`/api/health/${userId}`);
  return response.data;
};

export default apiClient;
