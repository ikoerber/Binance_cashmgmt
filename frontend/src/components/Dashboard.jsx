/**
 * Dashboard - Portfolio Übersicht
 */
import { useQuery } from '@tanstack/react-query';
import { getPortfolio, getDailyPerformance } from '../api/client';
import { useAppState } from '../contexts/AppStateContext';
import { formatNumber, formatEUR, formatBTC } from '../utils/formatters';
import './Dashboard.css';

// Preis auf 50 EUR runden, damit der queryKey nicht bei jedem Tick wechselt
const roundPrice = (p) => Math.round(p / 50) * 50;

const Dashboard = () => {
  const { userId, marketPrice } = useAppState();
  const stablePrice = roundPrice(marketPrice);

  // Portfolio wird per WebSocket balance_update Event invalidiert (kein Polling noetig)
  // stablePrice im queryKey: Refetch nur bei >= 50 EUR Aenderung
  const { data: portfolio, isLoading, error } = useQuery({
    queryKey: ['portfolio', userId, stablePrice],
    queryFn: () => getPortfolio(userId, marketPrice),
  });

  const { data: daily } = useQuery({
    queryKey: ['daily-performance', userId, stablePrice],
    queryFn: () => getDailyPerformance(userId, marketPrice),
  });

  if (isLoading) return <div className="loading">Lade Portfolio...</div>;
  if (error) return <div className="error">Fehler: {error.message}</div>;
  if (!portfolio) return null;

  const formatCurrency = formatEUR;

  const externalNet = parseFloat(portfolio.external_net_eur);
  const depotValue = parseFloat(portfolio.market_value_eur) + parseFloat(portfolio.eur_available);
  const depotPnl = depotValue - externalNet;
  const depotPnlPct = externalNet !== 0 ? (depotPnl / externalNet) * 100 : 0;

  return (
    <div className="dashboard">
      <h1>BTC/EUR Portfolio Dashboard</h1>

      {/* Depot-Übersicht: Eingezahlt → Bestand → Performance */}
      <div className="depot-flow">
        <div className="flow-card">
          <h3>Eingezahlt</h3>
          <div className="flow-value">{formatCurrency(externalNet)}</div>
        </div>
        <div className="flow-arrow">=</div>
        <div className="flow-card">
          <h3>EUR verfügbar</h3>
          <div className="flow-value">{formatCurrency(portfolio.eur_available)}</div>
        </div>
        <div className="flow-arrow">+</div>
        <div className="flow-card">
          <h3>BTC Bestand</h3>
          <div className="flow-value">{formatBTC(portfolio.btc_qty)}</div>
          <div className="flow-sub">Wert: {formatCurrency(portfolio.market_value_eur)}</div>
        </div>
        <div className="flow-arrow">=</div>
        <div className={`flow-card flow-result ${depotPnl >= 0 ? 'positive' : 'negative'}`}>
          <h3>Depot-Performance</h3>
          <div className="flow-value">{depotPnl >= 0 ? '+' : ''}{formatCurrency(depotPnl)}</div>
          <div className="flow-sub">{depotPnlPct >= 0 ? '+' : ''}{formatNumber(depotPnlPct)}%</div>
        </div>
      </div>

      {/* Tages-Performance */}
      {daily && (
        <div className="daily-performance">
          <h2>Tages-Performance</h2>
          <div className="daily-grid">
            <div className={`card ${parseFloat(daily.realized_pnl_today_eur) >= 0 ? 'positive' : 'negative'}`}>
              <h3>Realisierte P&L heute</h3>
              <div className="value">
                {parseFloat(daily.realized_pnl_today_eur) >= 0 ? '+' : ''}
                {formatCurrency(daily.realized_pnl_today_eur)}
              </div>
              <div className="sub-value">
                {daily.sells_count_today} Verkäufe ({formatBTC(daily.sells_volume_btc_today)})
              </div>
            </div>

            <div className="card">
              <h3>Neue Buys heute</h3>
              <div className="value">{daily.buys_count_today} Trades</div>
              <div className="sub-value">
                {formatBTC(daily.buys_volume_btc_today)} / {formatCurrency(daily.buys_volume_eur_today)}
              </div>
            </div>

            <div className={`card ${parseFloat(daily.unrealized_pnl_change_eur) >= 0 ? 'positive' : 'negative'}`}>
              <h3>Unrealisierte Veränderung</h3>
              <div className="value">
                {parseFloat(daily.unrealized_pnl_change_eur) >= 0 ? '+' : ''}
                {formatCurrency(daily.unrealized_pnl_change_eur)}
              </div>
              <div className="sub-value">
                Tagesbeginn: {formatCurrency(daily.unrealized_pnl_start_of_day_eur)}
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
