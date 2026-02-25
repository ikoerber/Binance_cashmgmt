/**
 * Dashboard - Portfolio Übersicht
 */
import { useQuery } from '@tanstack/react-query';
import { getPortfolio, getDailyPerformance } from '../api/client';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import { formatNumber, formatQuote, formatBase } from '../utils/formatters';
import { getBaseLabel, getQuoteLabel } from '../utils/symbolRegistry';
import CombinedScoreWidget from './CombinedScoreWidget';
import './Dashboard.css';

// Preis auf 50 EUR runden, damit der queryKey nicht bei jedem Tick wechselt
const roundPrice = (p) => Math.round(p / 50) * 50;

const Dashboard = () => {
  const { userId } = useUser();
  const { symbol: activeSymbol, marketPrice } = useSymbol();
  const stablePrice = roundPrice(marketPrice);

  // Portfolio wird per WebSocket balance_update Event invalidiert (kein Polling noetig)
  // stablePrice im queryKey: Refetch nur bei >= 50 EUR Aenderung
  const { data: portfolio, isLoading, error } = useQuery({
    queryKey: ['portfolio', activeSymbol, userId, stablePrice],
    queryFn: () => getPortfolio(userId, marketPrice, activeSymbol),
  });

  const { data: daily } = useQuery({
    queryKey: ['daily-performance', activeSymbol, userId, stablePrice],
    queryFn: () => getDailyPerformance(userId, marketPrice, activeSymbol),
  });

  if (isLoading) return <div className="loading">Lade Portfolio...</div>;
  if (error) return <div className="error">Fehler: {error.message}</div>;
  if (!portfolio) return null;

  const fmtQuote = (num) => formatQuote(num, activeSymbol);

  const externalNet = parseFloat(portfolio.external_net_quote);
  // Per-Symbol Depot P&L aus Backend (realisiert + unrealisiert)
  const depotPnl = portfolio.depot_pnl_quote != null
    ? parseFloat(portfolio.depot_pnl_quote)
    : parseFloat(portfolio.market_value_tracked_quote) + parseFloat(portfolio.quote_available) - externalNet;
  const depotPnlPct = externalNet !== 0 ? (depotPnl / externalNet) * 100 : 0;

  return (
    <div className="dashboard">
      <h1>{getBaseLabel(activeSymbol)}/{getQuoteLabel(activeSymbol)} Portfolio Dashboard</h1>

      {/* Combined Score Hero Widget */}
      <CombinedScoreWidget />

      {/* Depot-Übersicht: Eingezahlt → Bestand → Performance */}
      <div className="depot-flow">
        <div className="flow-card">
          <h3>Eingezahlt</h3>
          <div className="flow-value">{fmtQuote(externalNet)}</div>
        </div>
        <div className="flow-arrow">=</div>
        <div className="flow-card">
          <h3>{getQuoteLabel(activeSymbol)} verfügbar</h3>
          <div className="flow-value">{fmtQuote(portfolio.quote_available)}</div>
        </div>
        <div className="flow-arrow">+</div>
        <div className="flow-card">
          <h3>{getBaseLabel(activeSymbol)} Bestand</h3>
          <div className="flow-value">{formatBase(portfolio.base_qty, activeSymbol)}</div>
          <div className="flow-sub">Wert: {fmtQuote(portfolio.market_value_quote)}</div>
        </div>
        <div className="flow-arrow">=</div>
        <div className={`flow-card flow-result ${depotPnl >= 0 ? 'positive' : 'negative'}`}>
          <h3>Depot-Performance</h3>
          <div className="flow-value">{depotPnl >= 0 ? '+' : ''}{fmtQuote(depotPnl)}</div>
          <div className="flow-sub">{depotPnlPct >= 0 ? '+' : ''}{formatNumber(depotPnlPct)}%</div>
        </div>
      </div>

      {/* Tages-Performance */}
      {daily && (
        <div className="daily-performance">
          <h2>Tages-Performance</h2>
          <div className="daily-grid">
            <div className={`card ${parseFloat(daily.realized_pnl_today_quote) >= 0 ? 'positive' : 'negative'}`}>
              <h3>Realisierte P&L heute</h3>
              <div className="value">
                {parseFloat(daily.realized_pnl_today_quote) >= 0 ? '+' : ''}
                {fmtQuote(daily.realized_pnl_today_quote)}
              </div>
              <div className="sub-value">
                {daily.sells_count_today} Verkäufe ({formatBase(daily.sells_volume_base_today, activeSymbol)})
              </div>
            </div>

            <div className="card">
              <h3>Neue Buys heute</h3>
              <div className="value">{daily.buys_count_today} Trades</div>
              <div className="sub-value">
                {formatBase(daily.buys_volume_base_today, activeSymbol)} / {fmtQuote(daily.buys_volume_quote_today)}
              </div>
            </div>

            <div className={`card ${parseFloat(daily.unrealized_pnl_change_quote) >= 0 ? 'positive' : 'negative'}`}>
              <h3>Unrealisierte Veränderung</h3>
              <div className="value">
                {parseFloat(daily.unrealized_pnl_change_quote) >= 0 ? '+' : ''}
                {fmtQuote(daily.unrealized_pnl_change_quote)}
              </div>
              <div className="sub-value">
                Tagesbeginn: {fmtQuote(daily.unrealized_pnl_start_of_day_quote)}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="info-box">
        <p><strong>Letzte Aktualisierung:</strong> {new Date(portfolio.timestamp).toLocaleString('de-DE')}</p>
      </div>
    </div>
  );
};

export default Dashboard;
