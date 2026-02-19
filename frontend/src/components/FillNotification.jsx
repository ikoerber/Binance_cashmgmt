/**
 * Fill Notification Toast
 *
 * Zeigt eine kurze Benachrichtigung wenn ein Fill via WebSocket Phase 3
 * in Echtzeit verarbeitet wurde. Auto-Dismiss nach 5 Sekunden.
 *
 * Lebt ausserhalb von SymbolLayout — Symbol wird aus dem Fill-Event gelesen.
 */
import { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import { formatBase, formatQuote } from '../utils/formatters';
import './FillNotification.css';

export default function FillNotification() {
  const { lastFillEvent } = useWebSocket();
  const [visible, setVisible] = useState(false);
  const [notification, setNotification] = useState(null);
  const timeoutRef = useRef(null);

  useEffect(() => {
    if (!lastFillEvent?.data) return;

    const fill = lastFillEvent.data;
    setNotification({
      side: fill.side,
      qty: fill.qty,
      price: fill.price,
      action: fill.action,
      symbol: fill.symbol || 'BTCEUR',
    });
    setVisible(true);

    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setVisible(false), 5000);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [lastFillEvent]);

  if (!visible || !notification) return null;

  const isBuy = notification.side === 'BUY';

  return (
    <div className={`fill-notification ${isBuy ? 'fill-buy' : 'fill-sell'}`}>
      <div className="fill-notification-icon">
        {isBuy ? '\u25B2' : '\u25BC'}
      </div>
      <div className="fill-notification-content">
        <strong>{isBuy ? 'Buy' : 'Sell'} Fill verarbeitet</strong>
        <span className="fill-notification-detail">
          {formatBase(notification.qty, notification.symbol)} @ {formatQuote(notification.price, notification.symbol)}
        </span>
        <small className="fill-notification-action">
          {notification.action === 'lot_created' ? 'Neues Lot erstellt' : 'Sell allokiert'}
        </small>
      </div>
      <button
        className="fill-notification-close"
        onClick={() => setVisible(false)}
        aria-label="Schliessen"
      >
        \u00D7
      </button>
    </div>
  );
}
