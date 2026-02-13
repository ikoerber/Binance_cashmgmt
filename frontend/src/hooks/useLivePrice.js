/**
 * Custom Hook für Live BTC/EUR Preis
 *
 * Pollt Binance API alle 10 Sekunden
 */
import { useState, useEffect } from 'react';
import axios from 'axios';

const BINANCE_API = 'https://api.binance.com/api/v3/ticker/price';

export const useLivePrice = (symbol = 'BTCEUR', intervalMs = 10000) => {
  const [price, setPrice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    let isMounted = true;
    let intervalId;

    const fetchPrice = async () => {
      try {
        const response = await axios.get(BINANCE_API, {
          params: { symbol },
        });

        if (isMounted) {
          const newPrice = parseFloat(response.data.price);
          setPrice(newPrice);
          setLastUpdate(new Date());
          setLoading(false);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message);
          setLoading(false);
        }
      }
    };

    // Initial fetch
    fetchPrice();

    // Poll every intervalMs
    intervalId = setInterval(fetchPrice, intervalMs);

    return () => {
      isMounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [symbol, intervalMs]);

  return { price, loading, error, lastUpdate };
};
