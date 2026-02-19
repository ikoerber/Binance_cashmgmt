/**
 * LotSummaryCards - KPI-Kacheln fuer TradeLots
 *
 * Zeigt: Kosten offener Positionen, Menge Offen (gefiltert), Erholungspreis
 *
 * Erholungspreis-Formel (konsistent mit Backend §2.1.4):
 *   P = (total_qty × marktpreis + |deficit|) / (total_qty × (1 - fee_rate))
 *   Wird nur angezeigt wenn Depoterfolg < 0
 */
import { useAppState } from '../contexts/AppStateContext';
import { useQuery } from '@tanstack/react-query';
import { getSettings } from '../api/client';
import { formatEUR, formatBase, formatNumber } from '../utils/formatters';

const DEFAULT_FEE_RATE = 0.001; // 0.1% Binance Spot Fee Fallback

const LotSummaryCards = ({ openCostSum, filteredOpenQtySum, totalOpenQty, depotPnl }) => {
  const { userId, marketPrice, activeSymbol } = useAppState();

  const { data: settings } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
    staleTime: 60_000,
  });

  // Fee-Rate: aus Settings oder Default
  const feeRate = settings?.fee_rate != null
    ? parseFloat(settings.fee_rate)
    : DEFAULT_FEE_RATE;

  const recoveryPrice =
    depotPnl !== null && depotPnl < 0 && totalOpenQty > 0
      ? (totalOpenQty * marketPrice + Math.abs(depotPnl)) / (totalOpenQty * (1 - feeRate))
      : null;

  return (
    <div className="lots-summary">
      <div className="summary-card">
        <span className="summary-label">Kosten offene Positionen</span>
        <span className="summary-value">{formatEUR(openCostSum)}</span>
      </div>
      <div className="summary-card">
        <span className="summary-label">Menge Offen (gefiltert)</span>
        <span className="summary-value">{formatBase(filteredOpenQtySum, activeSymbol)}</span>
      </div>
      {recoveryPrice !== null && (
        <div className="summary-card recovery-card">
          <span className="summary-label">Erholungspreis</span>
          <span className="summary-value recovery-value">{formatEUR(recoveryPrice)}</span>
          <span className="summary-sub">
            +{formatNumber(((recoveryPrice / marketPrice) - 1) * 100, 1)}% über Markt | Deficit: {formatEUR(Math.abs(depotPnl))}
          </span>
        </div>
      )}
    </div>
  );
};

export default LotSummaryCards;
