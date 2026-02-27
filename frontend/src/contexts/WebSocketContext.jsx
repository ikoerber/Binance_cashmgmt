/**
 * WebSocket Context Provider
 *
 * Verwaltet die WebSocket-Verbindung zum Backend und stellt Echtzeit-Daten bereit:
 * - Live Preise fuer alle bekannten Paare (Phase 1, Multi-Pair)
 * - Order-Status-Updates (Phase 2)
 * - Balance-Updates (Phase 2)
 *
 * Graceful Degradation: Automatischer Fallback zu REST-Polling bei WS-Fehler.
 */
import { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

const WebSocketContext = createContext(null);

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8100';
const API_KEY = import.meta.env.VITE_API_KEY || '';

// HTTP(S) URL zu WS(S) URL konvertieren
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

export const WebSocketProvider = ({ userId = 'user_123', children }) => {
  const queryClient = useQueryClient();

  // Connection State
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);

  // Phase 1: Prices (Multi-Pair Map)
  const [prices, setPrices] = useState({});
  const [priceLastUpdates, setPriceLastUpdates] = useState({});

  // Phase 2: Orders + Balances
  const [lastOrderUpdate, setLastOrderUpdate] = useState(null);
  const [lastBalanceUpdate, setLastBalanceUpdate] = useState(null);

  // Phase 3: Fill Events
  const [lastFillEvent, setLastFillEvent] = useState(null);

  // Backtest Progress (Phase 15)
  const [backtestProgress, setBacktestProgress] = useState(null);
  const backtestProgressResetRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const url = `${WS_BASE_URL}/ws/${userId}/stream`;
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      console.error('WebSocket Verbindungsfehler:', err);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      // First-Message-Auth: API-Key als Nachricht statt URL-Parameter
      if (API_KEY) {
        ws.send(JSON.stringify({ action: 'auth', api_key: API_KEY }));
      } else {
        // Kein API-Key konfiguriert — direkt subscriben
        setConnected(true);
        reconnectAttempts.current = 0;
        ws.send(JSON.stringify({ action: 'subscribe', channel: 'user_data' }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'auth_ok':
            console.log('WebSocket authentifiziert');
            setConnected(true);
            reconnectAttempts.current = 0;
            // Nach erfolgreicher Auth: User Data Channel subscriben
            wsRef.current?.send(JSON.stringify({ action: 'subscribe', channel: 'user_data' }));
            break;

          case 'auth_error':
            console.error('WebSocket Auth fehlgeschlagen:', data.detail);
            wsRef.current?.close(4001, 'Auth failed');
            return;

          case 'price_update': {
            const p = parseFloat(data.price);
            if (isNaN(p) || !isFinite(p) || p <= 0) break;
            const sym = data.symbol || 'BTCEUR';
            setPrices(prev => ({ ...prev, [sym]: p }));
            setPriceLastUpdates(prev => ({ ...prev, [sym]: new Date(data.timestamp) }));
            break;
          }

          case 'order_update': {
            setLastOrderUpdate(data);
            // Symbol-scoped Invalidation — nur betroffenes Paar refetchen
            const orderSym = data.symbol || 'BTCEUR';
            queryClient.invalidateQueries({ queryKey: ['orders', orderSym] });
            queryClient.invalidateQueries({ queryKey: ['lots', orderSym] });
            queryClient.invalidateQueries({ queryKey: ['portfolio', orderSym] });
            break;
          }

          case 'balance_update': {
            setLastBalanceUpdate(data);
            const balSym = data.symbol || 'BTCEUR';
            queryClient.invalidateQueries({ queryKey: ['portfolio', balSym] });
            break;
          }

          case 'fill_processed': {
            setLastFillEvent(data);
            // Fill verarbeitet — symbol-scoped Queries invalidieren
            const fillSym = data.symbol || data.data?.symbol || 'BTCEUR';
            queryClient.invalidateQueries({ queryKey: ['lots', fillSym] });
            queryClient.invalidateQueries({ queryKey: ['portfolio', fillSym] });
            queryClient.invalidateQueries({ queryKey: ['orders', fillSym] });
            break;
          }

          case 'backtest_progress': {
            const progressData = data.data || data;
            setBacktestProgress(progressData);
            // Auto-reset nach Abschluss oder Abbruch (nach 2s damit UI 100% anzeigen kann)
            if (progressData.phase === 'complete' || progressData.phase === 'cancelled') {
              if (backtestProgressResetRef.current) clearTimeout(backtestProgressResetRef.current);
              backtestProgressResetRef.current = setTimeout(() => setBacktestProgress(null), 2000);
            }
            break;
          }

          case 'dry_run_decision': {
            queryClient.invalidateQueries({ queryKey: ['dry-run-decisions'] });
            queryClient.invalidateQueries({ queryKey: ['dry-run-status'] });
            queryClient.invalidateQueries({ queryKey: ['dry-run-portfolio'] });
            break;
          }

          case 'dry_run_status': {
            queryClient.invalidateQueries({ queryKey: ['dry-run-status'] });
            queryClient.invalidateQueries({ queryKey: ['dry-run-portfolio'] });
            break;
          }

          case 'dry_run_portfolio_update': {
            queryClient.invalidateQueries({ queryKey: ['dry-run-portfolio'] });
            queryClient.invalidateQueries({ queryKey: ['dry-run-status'] });
            break;
          }

          case 'pong':
            // Heartbeat Response — nichts zu tun
            break;

          default:
            break;
        }
      } catch (err) {
        console.error('WebSocket Message Parse Fehler:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket Fehler:', error);
    };

    ws.onclose = (event) => {
      console.log(`WebSocket getrennt (Code: ${event.code})`);
      setConnected(false);
      wsRef.current = null;

      // Nicht reconnecten bei Auth-Fehler
      if (event.code === 4001) {
        console.error('WebSocket Auth fehlgeschlagen — kein Reconnect');
        return;
      }

      scheduleReconnect();
    };

    wsRef.current = ws;
  }, [userId, queryClient]);

  const scheduleReconnect = useCallback(() => {
    // Exponential Backoff: 1s → 2s → 4s → ... → 30s max
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
    reconnectAttempts.current += 1;

    console.log(`WebSocket Reconnect in ${delay / 1000}s (Versuch ${reconnectAttempts.current})`);

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    connect();

    // Heartbeat alle 30s
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'ping' }));
      }
    }, 30000);

    return () => {
      clearInterval(heartbeat);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const value = {
    connected,
    prices,
    priceLastUpdates,
    // Backward-compat: single price (BTCEUR)
    price: prices['BTCEUR'] ?? null,
    priceLastUpdate: priceLastUpdates['BTCEUR'] ?? null,
    lastOrderUpdate,
    lastBalanceUpdate,
    lastFillEvent,
    backtestProgress,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};

/**
 * Basis-Hook fuer WebSocket Context.
 */
export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket muss innerhalb von WebSocketProvider verwendet werden');
  }
  return context;
};

/**
 * Live-Preis Hook: WebSocket wenn verbunden, REST-Polling als Fallback.
 * Unterstuetzt Multi-Pair via symbol Parameter.
 */
// Schwellwert fuer "starke Aenderung" in Prozent
const LARGE_CHANGE_THRESHOLD_PCT = 1.0;
// Dauer der Flash-Animation in ms
const FLASH_DURATION_MS = 3000;

export const useLivePrice = (symbol = 'BTCEUR', intervalMs = 10000) => {
  const { connected, prices, priceLastUpdates } = useWebSocket();

  const wsPrice = prices[symbol] ?? null;
  const wsPriceLastUpdate = priceLastUpdates[symbol] ?? null;

  // Fallback: REST-Polling wenn WebSocket nicht verbunden oder kein Preis fuer Symbol
  const [pollingPrice, setPollingPrice] = useState(null);
  const [pollingLoading, setPollingLoading] = useState(true);
  const [pollingError, setPollingError] = useState(null);
  const [pollingLastUpdate, setPollingLastUpdate] = useState(null);

  // Richtung und Aenderungstracking
  const prevPriceRef = useRef(null);
  const [direction, setDirection] = useState(null); // 'up' | 'down' | null
  const [changePct, setChangePct] = useState(0);
  const [isFlashing, setIsFlashing] = useState(false);
  const flashTimeoutRef = useRef(null);

  // Aktuellen Preis bestimmen (WS oder Polling)
  const currentPrice = (connected && wsPrice !== null) ? wsPrice : pollingPrice;

  // Richtung und Aenderung berechnen wenn sich der Preis aendert
  useEffect(() => {
    if (currentPrice === null) return;

    const prev = prevPriceRef.current;
    if (prev !== null && prev !== currentPrice) {
      // Richtung
      if (currentPrice > prev) {
        setDirection('up');
      } else if (currentPrice < prev) {
        setDirection('down');
      }

      // Prozentuale Aenderung
      const pctChange = Math.abs(((currentPrice - prev) / prev) * 100);
      setChangePct(pctChange);

      // Flash bei starker Aenderung
      if (pctChange >= LARGE_CHANGE_THRESHOLD_PCT) {
        setIsFlashing(true);
        if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
        flashTimeoutRef.current = setTimeout(() => setIsFlashing(false), FLASH_DURATION_MS);
      }
    }

    prevPriceRef.current = currentPrice;
  }, [currentPrice]);

  // Cleanup Flash-Timeout
  useEffect(() => {
    return () => {
      if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    // Kein Polling noetig wenn WebSocket Preis liefert
    if (connected && wsPrice !== null) {
      return;
    }

    let isMounted = true;
    let intervalId;

    const fetchPrice = async () => {
      try {
        const response = await fetch(
          `https://api.binance.com/api/v3/ticker/price?symbol=${symbol}`
        );
        const data = await response.json();

        if (isMounted) {
          setPollingPrice(parseFloat(data.price));
          setPollingLastUpdate(new Date());
          setPollingLoading(false);
          setPollingError(null);
        }
      } catch (err) {
        if (isMounted) {
          setPollingError(err.message);
          setPollingLoading(false);
        }
      }
    };

    fetchPrice();
    intervalId = setInterval(fetchPrice, intervalMs);

    return () => {
      isMounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [connected, wsPrice, symbol, intervalMs]);

  const extra = { direction, changePct, isFlashing };

  // WebSocket hat Prioritaet
  if (connected && wsPrice !== null) {
    return {
      price: wsPrice,
      loading: false,
      error: null,
      lastUpdate: wsPriceLastUpdate,
      source: 'websocket',
      ...extra,
    };
  }

  // Fallback zu Polling
  return {
    price: pollingPrice,
    loading: pollingLoading,
    error: pollingError,
    lastUpdate: pollingLastUpdate,
    source: 'polling',
    ...extra,
  };
};
