/**
 * API Client für Backend
 */
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Portfolio API
export const getPortfolio = async (userId, marketPrice) => {
  const response = await apiClient.get(`/api/portfolio/${userId}`, {
    params: { market_price: marketPrice },
  });
  return response.data;
};

export const getDailyPerformance = async (userId, marketPrice) => {
  const response = await apiClient.get(`/api/portfolio/${userId}/daily`, {
    params: { market_price: marketPrice },
  });
  return response.data;
};

// Lots API
export const getLots = async (userId, status = null, limit = 100, offset = 0, fromDate = null, toDate = null) => {
  const response = await apiClient.get(`/api/lots/${userId}`, {
    params: { status, limit, offset, from_date: fromDate, to_date: toDate },
  });
  return response.data;
};

export const getLotDetail = async (userId, lotId) => {
  const response = await apiClient.get(`/api/lots/${userId}/${lotId}`);
  return response.data;
};

// Orders API
export const getOrdersForUser = async (userId, status = null) => {
  const response = await apiClient.get(`/api/orders/${userId}/list`, {
    params: { status },
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
export const getPairingSuggestions = async (userId, marketPrice, thresholdPct = 0.05) => {
  const response = await apiClient.get(`/api/pairing/${userId}/suggestions`, {
    params: { market_price: marketPrice, threshold_pct: thresholdPct },
  });
  return response.data;
};

export const simulatePairing = async (userId, pairingId, marketPrice, feePct = 0.001, feeBufferPct = 0.002) => {
  const response = await apiClient.get(`/api/pairing/${userId}/simulate/${pairingId}`, {
    params: { market_price: marketPrice, fee_pct: feePct, fee_buffer_pct: feeBufferPct },
  });
  return response.data;
};

export const createPairing = async (userId, items, thresholdPct) => {
  const response = await apiClient.post(`/api/pairing/${userId}/create`, {
    items,
    threshold_pct: thresholdPct,
  });
  return response.data;
};

export const listPairings = async (userId, status = null) => {
  const response = await apiClient.get(`/api/pairing/${userId}/list`, {
    params: { status },
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

export const executePairing = async (userId, pairingId, marketPrice, feeBufferPct = 0.002) => {
  const response = await apiClient.post(`/api/pairing/${userId}/${pairingId}/execute`, null, {
    params: { market_price: marketPrice, fee_buffer_pct: feeBufferPct },
  });
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

export const reconcileBalances = async (userId) => {
  const response = await apiClient.post(`/api/reconciliation/${userId}/balances`);
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

// Macro Signal API
export const getMacroSignals = async (interval = '15') => {
  const response = await apiClient.get('/api/macro/signals', {
    params: { interval },
  });
  return response.data;
};

export default apiClient;
