/**
 * WebSocket Context Provider
 *
 * Verwaltet die WebSocket-Verbindung zum Backend und stellt Echtzeit-Daten bereit:
 * - Live BTC/EUR Preis (Phase 1)
 * - Order-Status-Updates (Phase 2)
 * - Balance-Updates (Phase 2)
 *
 * Graceful Degradation: Automatischer Fallback zu REST-Polling bei WS-Fehler.
 */
import { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

const WebSocketContext = createContext(null);

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
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

  // Phase 1: Price
  const [price, setPrice] = useState(null);
  const [priceLastUpdate, setPriceLastUpdate] = useState(null);

  // Phase 2: Orders + Balances
  const [lastOrderUpdate, setLastOrderUpdate] = useState(null);
  const [lastBalanceUpdate, setLastBalanceUpdate] = useState(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const url = `${WS_BASE_URL}/ws/${userId}/stream?X-API-Key=${encodeURIComponent(API_KEY)}`;
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      console.error('WebSocket Verbindungsfehler:', err);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      console.log('WebSocket verbunden');
      setConnected(true);
      reconnectAttempts.current = 0;

      // User Data Channel subscriben (Phase 2)
      ws.send(JSON.stringify({ action: 'subscribe', channel: 'user_data' }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'price_update':
            setPrice(parseFloat(data.price));
            setPriceLastUpdate(new Date(data.timestamp));
            break;

          case 'order_update':
            setLastOrderUpdate(data);
            // TanStack Query Cache invalidieren — Komponenten refetchen automatisch
            queryClient.invalidateQueries({ queryKey: ['orders'] });
            queryClient.invalidateQueries({ queryKey: ['lots'] });
            queryClient.invalidateQueries({ queryKey: ['portfolio'] });
            break;

          case 'balance_update':
            setLastBalanceUpdate(data);
            queryClient.invalidateQueries({ queryKey: ['portfolio'] });
            break;

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
    price,
    priceLastUpdate,
    lastOrderUpdate,
    lastBalanceUpdate,
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
 * Drop-in Replacement fuer hooks/useLivePrice.js
 *
 * Nutzt WebSocket wenn verbunden, faellt automatisch auf REST-Polling zurueck.
 */
export const useLivePrice = (symbol = 'BTCEUR', intervalMs = 10000) => {
  const { connected, price: wsPrice, priceLastUpdate } = useWebSocket();

  // Fallback: REST-Polling wenn WebSocket nicht verbunden
  const [pollingPrice, setPollingPrice] = useState(null);
  const [pollingLoading, setPollingLoading] = useState(true);
  const [pollingError, setPollingError] = useState(null);
  const [pollingLastUpdate, setPollingLastUpdate] = useState(null);

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

  // WebSocket hat Prioritaet
  if (connected && wsPrice !== null) {
    return {
      price: wsPrice,
      loading: false,
      error: null,
      lastUpdate: priceLastUpdate,
      source: 'websocket',
    };
  }

  // Fallback zu Polling
  return {
    price: pollingPrice,
    loading: pollingLoading,
    error: pollingError,
    lastUpdate: pollingLastUpdate,
    source: 'polling',
  };
};
