import { useState, useRef, useEffect, useCallback } from 'react';

/**
 * Shared notification hook — ersetzt die in 5 Komponenten duplizierte
 * message/timer-Logik (LotsTable, PairingPanel, Orderblock, Settings, Reconciliation).
 *
 * @param {number} defaultTimeout - Auto-Dismiss in ms (Default: 5000)
 * @returns {{ message, showMessage, dismissMessage }}
 */
const useNotification = (defaultTimeout = 5000) => {
  const [message, setMessage] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, []);

  const showMessage = useCallback((type, text, timeout) => {
    setMessage({ type, text });
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setMessage(null), timeout ?? defaultTimeout);
  }, [defaultTimeout]);

  const dismissMessage = useCallback(() => {
    setMessage(null);
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  return { message, showMessage, dismissMessage };
};

export default useNotification;
