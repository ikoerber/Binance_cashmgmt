/**
 * Shared Formatting Utilities
 *
 * Zentrale Formatierungsfunktionen fuer alle Komponenten.
 * German locale (de-DE) fuer Zahlen, Waehrungen, Daten.
 */

export const formatNumber = (num, decimals = 2) => {
  if (num === null || num === undefined) return 'N/A';
  return parseFloat(num).toLocaleString('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
};

export const formatEUR = (num) => `${formatNumber(num, 2)} \u20ac`;

export const formatBTC = (num) => `${formatNumber(num, 8)} BTC`;

export const formatPct = (num) => `${num >= 0 ? '+' : ''}${formatNumber(num, 2)}%`;

export const formatDate = (isoString) => {
  const d = new Date(isoString);
  return d.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

export const formatTime = (isoString) => {
  const d = new Date(isoString);
  return d.toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};
