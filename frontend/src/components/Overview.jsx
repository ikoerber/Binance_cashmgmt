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
import { getAllSymbols, getPairLabel, getBaseLabel, getBaseAsset, getQuoteAsset } from '../utils/symbolRegistry';
import { formatEUR, formatBase, formatNumber } from '../utils/formatters';
import './Overview.css';

/** Read chart palette from CSS custom properties (theme-aware) */
const getChartColors = () => {
  const style = getComputedStyle(document.documentElement);
  return [
    style.getPropertyValue('--color-chart-1').trim() || '#667eea',
    style.getPropertyValue('--color-chart-2').trim() || '#f59e0b',
    style.getPropertyValue('--color-chart-3').trim() || '#10b981',
    style.getPropertyValue('--color-chart-4').trim() || '#ef4444',
    style.getPropertyValue('--color-chart-5').trim() || '#8b5cf6',
  ];
};

const Overview = () => {
  const { userId } = useUser();
  const { prices } = useWebSocket();
  const navigate = useNavigate();
  const symbols = getAllSymbols();
  const COLORS = getChartColors();

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
    const marketValue = parseFloat(portfolio.market_value_quote || 0);
    const externalNet = parseFloat(portfolio.external_net_quote || 0);
    // Per-Symbol Depot P&L aus Backend (realisiert + unrealisiert)
    const depotPnl = portfolio.depot_pnl_quote != null ? parseFloat(portfolio.depot_pnl_quote) : 0;
    const depotPnlPct = externalNet !== 0 ? (depotPnl / externalNet) * 100 : 0;

    return {
      sym,
      livePrice,
      loaded: true,
      baseQty,
      marketValue,
      externalNet,
      depotPnl,
      depotPnlPct,
    };
  });

  // Aggregation: Per-Symbol depot_pnl_quote summieren
  const loadedSummaries = symbolSummaries.filter(s => s.loaded);
  const btcEurPrice = prices['BTCEUR'] || 0;
  const toEur = (s, val) => getQuoteAsset(s.sym) !== 'EUR' && btcEurPrice ? val * btcEurPrice : val;
  // Gesamt-Marktwert: Binance-Balancen dedupliziert nach Base-Asset
  const binanceValueByBase = {};
  for (const s of loadedSummaries) {
    const base = getBaseAsset(s.sym);
    if (!(base in binanceValueByBase) || getQuoteAsset(s.sym) === 'EUR') {
      binanceValueByBase[base] = { value: toEur(s, s.marketValue), label: base };
    }
  }
  const totalMarketValue = Object.values(binanceValueByBase).reduce((sum, e) => sum + e.value, 0);
  const totalDepotPnl = loadedSummaries.reduce((sum, s) => sum + toEur(s, s.depotPnl), 0);
  // Eingezahlt: Deduplizieren nach Quote-Asset (EUR SEPA-Einzahlung ist fuer BTCEUR, ETHEUR, XRPEUR identisch)
  const externalByQuote = {};
  for (const s of loadedSummaries) {
    const quote = getQuoteAsset(s.sym);
    if (!(quote in externalByQuote)) externalByQuote[quote] = s.externalNet;
  }
  const totalExternalNet = Object.values(externalByQuote).reduce((sum, v) => sum + v, 0);
  const totalDepotPnlPct = totalExternalNet !== 0 ? (totalDepotPnl / totalExternalNet) * 100 : 0;
  // EUR Cash: Globale Binance-Balance (identisch fuer alle EUR-Paare, einmal auslesen)
  const eurCash = (() => {
    for (const q of portfolioQueries) {
      if (q.data?.quote_available != null && getQuoteAsset(q.data.symbol) === 'EUR') {
        return parseFloat(q.data.quote_available);
      }
    }
    return null;
  })();

  // Gesamt-Depotwert: Crypto-Marktwerte + EUR Cash
  const totalPortfolioValue = totalMarketValue + (eurCash || 0);

  // Pie Chart Data: Binance-Balancen dedupliziert nach Base-Asset (inkl. EUR Cash)
  const pieData = [
    ...Object.values(binanceValueByBase)
      .filter(e => e.value > 0)
      .map(e => ({ name: e.label, value: e.value })),
    ...(eurCash > 0 ? [{ name: 'EUR Cash', value: eurCash }] : []),
  ];

  return (
    <div className="overview-container">
      <div className="content">
        <h1>Portfolio Overview</h1>

        {anyLoading && <div className="overview-loading">Lade Portfolio-Daten...</div>}

        {/* Gesamt-Portfolio */}
        <div className="overview-total">
          <div className="overview-total-card">
            <h3>Gesamt-Depotwert</h3>
            <div className="overview-total-value">{formatEUR(totalPortfolioValue)}</div>
          </div>
          <div className="overview-total-card">
            <h3>Eingezahlt</h3>
            <div className="overview-total-value">{formatEUR(totalExternalNet)}</div>
          </div>
          {eurCash != null && (
            <div className="overview-total-card">
              <h3>EUR verfügbar</h3>
              <div className="overview-total-value">{formatEUR(eurCash)}</div>
            </div>
          )}
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
                      {s.livePrice
                        ? getQuoteAsset(s.sym) === 'EUR'
                          ? s.livePrice.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' \u20ac'
                          : s.livePrice.toFixed(8) + ' BTC'
                        : '\u2014'}
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
                        <span>
                          {formatEUR(getQuoteAsset(s.sym) !== 'EUR' && prices['BTCEUR']
                            ? s.marketValue * prices['BTCEUR']
                            : s.marketValue)}
                          {getQuoteAsset(s.sym) !== 'EUR' && <span className="overview-symbol-sub"> ({formatNumber(s.marketValue)} BTC)</span>}
                        </span>
                      </div>
                      <div className={`overview-symbol-row ${s.depotPnl >= 0 ? 'positive' : 'negative'}`}>
                        <span>P&L</span>
                        <span>
                          {s.depotPnl >= 0 ? '+' : ''}
                          {formatEUR(getQuoteAsset(s.sym) !== 'EUR' && prices['BTCEUR']
                            ? s.depotPnl * prices['BTCEUR']
                            : s.depotPnl)}
                          {' '}({s.depotPnlPct >= 0 ? '+' : ''}{formatNumber(s.depotPnlPct)}%)
                        </span>
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
