/**
 * Overview - Cross-Symbol Dashboard
 *
 * Aggregiertes Portfolio ueber alle bekannten Symbole.
 * Parallel-Fetch der Portfolio-Daten pro Symbol, Frontend-Aggregation.
 */
import { useNavigate } from 'react-router-dom';
import { useQueries } from '@tanstack/react-query';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { getPortfolio } from '../api/client';
import { useUser } from '../contexts/UserContext';
import { useWebSocket } from '../contexts/WebSocketContext';
import { getAllSymbols, getPairLabel, getBaseLabel } from '../utils/symbolRegistry';
import { formatEUR, formatBase, formatNumber } from '../utils/formatters';
import './Overview.css';

const COLORS = ['#667eea', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'];

const Overview = () => {
  const { userId } = useUser();
  const { prices } = useWebSocket();
  const navigate = useNavigate();
  const symbols = getAllSymbols();

  // Parallel portfolio queries fuer alle Symbole (useQueries statt useQuery in .map())
  const portfolioQueries = useQueries({
    queries: symbols.map(sym => {
      const price = prices[sym] || 0;
      const stablePrice = Math.round(price / 50) * 50;
      return {
        queryKey: ['portfolio', sym, userId, stablePrice],
        queryFn: () => getPortfolio(userId, price, sym),
        enabled: price > 0,
        staleTime: 30_000,
      };
    }),
  });

  const anyLoading = portfolioQueries.some(q => q.isLoading && q.fetchStatus !== 'idle');

  // Per-Symbol Summaries
  const symbolSummaries = symbols.map((sym, i) => {
    const query = portfolioQueries[i];
    const portfolio = query.data;
    const livePrice = prices[sym] || 0;

    if (!portfolio) return { sym, livePrice, loaded: false };

    const baseQty = parseFloat(portfolio.base_qty || 0);
    const eurAvailable = parseFloat(portfolio.eur_available || 0);
    const marketValue = parseFloat(portfolio.market_value_eur || 0);
    const externalNet = parseFloat(portfolio.external_net_eur || 0);
    const depotValue = marketValue + eurAvailable;
    const depotPnl = depotValue - externalNet;
    const depotPnlPct = externalNet !== 0 ? (depotPnl / externalNet) * 100 : 0;

    return {
      sym,
      livePrice,
      loaded: true,
      baseQty,
      eurAvailable,
      marketValue,
      externalNet,
      depotValue,
      depotPnl,
      depotPnlPct,
    };
  });

  // Aggregation
  const loadedSummaries = symbolSummaries.filter(s => s.loaded);
  const totalDepotValue = loadedSummaries.reduce((sum, s) => sum + s.depotValue, 0);
  const totalExternalNet = loadedSummaries.reduce((sum, s) => sum + s.externalNet, 0);
  const totalDepotPnl = totalDepotValue - totalExternalNet;
  const totalDepotPnlPct = totalExternalNet !== 0 ? (totalDepotPnl / totalExternalNet) * 100 : 0;

  // Pie Chart Data
  const pieData = loadedSummaries
    .filter(s => s.marketValue > 0)
    .map(s => ({
      name: getPairLabel(s.sym),
      value: s.marketValue,
    }));

  return (
    <div className="overview-container">
      <div className="content">
        <h1>Portfolio Overview</h1>

        {anyLoading && <div className="overview-loading">Lade Portfolio-Daten...</div>}

        {/* Gesamt-Portfolio */}
        <div className="overview-total">
          <div className="overview-total-card">
            <h3>Gesamt-Depotwert</h3>
            <div className="overview-total-value">{formatEUR(totalDepotValue)}</div>
          </div>
          <div className="overview-total-card">
            <h3>Eingezahlt</h3>
            <div className="overview-total-value">{formatEUR(totalExternalNet)}</div>
          </div>
          <div className={`overview-total-card ${totalDepotPnl >= 0 ? 'positive' : 'negative'}`}>
            <h3>Gesamt-Performance</h3>
            <div className="overview-total-value">
              {totalDepotPnl >= 0 ? '+' : ''}{formatEUR(totalDepotPnl)}
            </div>
            <div className="overview-total-sub">
              {totalDepotPnlPct >= 0 ? '+' : ''}{formatNumber(totalDepotPnlPct)}%
            </div>
          </div>
        </div>

        {/* Allocation Chart + Per-Symbol Cards */}
        <div className="overview-main">
          {/* Pie Chart */}
          {pieData.length > 0 && (
            <div className="overview-pie-section">
              <h2>Allokation nach Marktwert</h2>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {pieData.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => formatEUR(value)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Per-Symbol Cards */}
          <div className="overview-symbols">
            <h2>Per-Symbol</h2>
            <div className="overview-symbol-grid">
              {symbolSummaries.map((s) => (
                <div
                  key={s.sym}
                  className="overview-symbol-card"
                  onClick={() => navigate(`/s/${s.sym}`)}
                >
                  <div className="overview-symbol-header">
                    <span className="overview-symbol-label">{getPairLabel(s.sym)}</span>
                    <span className="overview-symbol-price">
                      {s.livePrice ? s.livePrice.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' \u20ac' : '\u2014'}
                    </span>
                  </div>
                  {s.loaded ? (
                    <div className="overview-symbol-body">
                      <div className="overview-symbol-row">
                        <span>{getBaseLabel(s.sym)} Bestand</span>
                        <span>{formatBase(s.baseQty, s.sym)}</span>
                      </div>
                      <div className="overview-symbol-row">
                        <span>Marktwert</span>
                        <span>{formatEUR(s.marketValue)}</span>
                      </div>
                      <div className={`overview-symbol-row ${s.depotPnl >= 0 ? 'positive' : 'negative'}`}>
                        <span>P&L</span>
                        <span>{s.depotPnl >= 0 ? '+' : ''}{formatEUR(s.depotPnl)} ({s.depotPnlPct >= 0 ? '+' : ''}{formatNumber(s.depotPnlPct)}%)</span>
                      </div>
                      <div className="overview-symbol-links">
                        <button onClick={(e) => { e.stopPropagation(); navigate(`/s/${s.sym}/lots`); }}>Lots</button>
                        <button onClick={(e) => { e.stopPropagation(); navigate(`/s/${s.sym}/combined`); }}>Signals</button>
                        <button onClick={(e) => { e.stopPropagation(); navigate(`/s/${s.sym}/orderblock`); }}>Orderblocks</button>
                      </div>
                    </div>
                  ) : (
                    <div className="overview-symbol-body overview-symbol-empty">
                      {prices[s.sym] ? 'Lade...' : 'Kein Preis verfuegbar'}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Overview;
