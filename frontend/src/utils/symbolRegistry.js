/**
 * Symbol Registry - Zentrales Mapping von Symbol → Base/Quote/Precision.
 *
 * Frontend-Gegenstueck zu backend/app/symbol_registry.py.
 * Alle Komponenten referenzieren diese Registry fuer dynamische Labels und Formatierung.
 */

export const KNOWN_PAIRS = {
  BTCEUR: { symbol: 'BTCEUR', base: 'BTC', quote: 'EUR', baseDecimals: 8, label: 'BTC/EUR' },
  ETHEUR: { symbol: 'ETHEUR', base: 'ETH', quote: 'EUR', baseDecimals: 5, label: 'ETH/EUR' },
  XRPEUR: { symbol: 'XRPEUR', base: 'XRP', quote: 'EUR', baseDecimals: 2, label: 'XRP/EUR' },
  XRPBTC: { symbol: 'XRPBTC', base: 'XRP', quote: 'BTC', baseDecimals: 2, label: 'XRP/BTC' },
};

export const parseSymbol = (symbol) => KNOWN_PAIRS[symbol];

export const getBaseDecimals = (symbol) => KNOWN_PAIRS[symbol]?.baseDecimals ?? 8;

export const getBaseLabel = (symbol) => KNOWN_PAIRS[symbol]?.base ?? symbol;

export const getPairLabel = (symbol) => KNOWN_PAIRS[symbol]?.label ?? symbol;

export const getAllSymbols = () => Object.keys(KNOWN_PAIRS);

export const getQuoteAsset = (symbol) => KNOWN_PAIRS[symbol]?.quote ?? 'EUR';

export const getQuoteDecimals = (symbol) => {
  const quote = getQuoteAsset(symbol);
  if (quote === 'EUR') return 2;
  if (quote === 'BTC') return 8;
  return 4;
};

export const getQuoteLabel = (symbol) => KNOWN_PAIRS[symbol]?.quote ?? 'EUR';
