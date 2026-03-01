/**
 * Overview - Cross-Symbol Dashboard
 *
 * Aggregiertes Portfolio ueber alle bekannten Symbole.
 * Parallel-Fetch der Portfolio-Daten pro Symbol, Frontend-Aggregation.
 */
import { useNavigate } from 'react-router-dom';
import { useQueries, useQuery } from '@tanstack/react-query';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { getPortfolio, getBnbFees } from '../api/client';
import { useUser } from '../contexts/UserContext';
import { useWebSocket } from '../contexts/WebSocketContext';
import { getBaseLabel, getBaseAsset, getQuoteAsset } from '../utils/symbolRegistry';
import { useActiveSymbols } from '../hooks/useActiveSymbols';
import { formatEUR, formatBase, formatNumber, formatPct } from '../utils/formatters';
import { useChartTheme } from '../hooks/useChartTheme';
import './Overview.css';

/** Read chart palette from CSS custom properties (theme-aware) */
const getChartColors = () => {
  const style = getComputedStyle(document.documentElement);
  return [
    style.getPropertyValue('--color-chart-1').trim() || '#818cf8',
    style.getPropertyValue('--color-chart-2').trim() || '#fbbf24',
    style.getPropertyValue('--color-chart-3').trim() || '#34d399',
    style.getPropertyValue('--color-chart-4').trim() || '#f87171',
    style.getPropertyValue('--color-chart-5').trim() || '#a78bfa',
  ];
};

const Overview = () => {
  const { userId } = useUser();
  const { prices } = useWebSocket();
  const navigate = useNavigate();
  const theme = useChartTheme();
  const { activeSymbols: symbols } = useActiveSymbols();
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

  // BNB Fee Summary
  const { data: bnbData } = useQuery({
    queryKey: ['bnb-fees', userId],
    queryFn: () => getBnbFees(userId),
    staleTime: 60_000,
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
                    label={({ name, percent, x, y, textAnchor }) => (
                      <text x={x} y={y} textAnchor={textAnchor} fill={theme.textPrimary} fontSize={13}>
                        {`${name} ${(percent * 100).toFixed(0)}%`}
                      </text>
                    )}
                    isAnimationActive={false}
                  >
                    {pieData.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value) => formatEUR(value)}
                    contentStyle={{
                      background: theme.bgCard,
                      border: `1px solid ${theme.border}`,
                      borderRadius: '8px',
                      color: theme.textPrimary,
                    }}
                    itemStyle={{ color: theme.textPrimary }}
                    labelStyle={{ color: theme.textSecondary }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Asset Table */}
          <div className="overview-asset-section">
            <h2>Assets</h2>
            <table className="overview-asset-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th className="text-right">Balance</th>
                  <th className="text-right">Wert EUR</th>
                  <th className="text-right">P&L %</th>
                </tr>
              </thead>
              <tbody>
                {symbolSummaries.map((s) => {
                  // Deduplicate: only show EUR-quoted pair per base asset (skip XRPBTC if XRPEUR exists)
                  const hasEurPair = symbolSummaries.some(
                    other => other.sym !== s.sym
                      && getBaseAsset(other.sym) === getBaseAsset(s.sym)
                      && getQuoteAsset(other.sym) === 'EUR'
                  );
                  if (getQuoteAsset(s.sym) !== 'EUR' && hasEurPair) return null;

                  const valueEur = toEur(s, s.marketValue);
                  return (
                    <tr
                      key={s.sym}
                      className="overview-asset-row"
                      onClick={() => navigate(`/s/${s.sym}`)}
                    >
                      <td className="asset-name">
                        <span className="asset-icon">{getBaseAsset(s.sym)}</span>
                        <span className="asset-label">{getBaseLabel(s.sym)}</span>
                      </td>
                      <td className="text-right">
                        {s.loaded ? formatBase(s.baseQty, s.sym) : '\u2014'}
                      </td>
                      <td className="text-right">
                        {s.loaded ? formatEUR(valueEur) : '\u2014'}
                      </td>
                      <td className={`text-right ${s.loaded ? (s.depotPnl >= 0 ? 'positive' : 'negative') : ''}`}>
                        {s.loaded ? formatPct(s.depotPnlPct) : '\u2014'}
                      </td>
                    </tr>
                  );
                })}
                {/* BNB Fee Row */}
                {bnbData && parseFloat(bnbData.bnb_balance) > 0 && (
                  <tr className="overview-asset-row overview-asset-row--muted">
                    <td className="asset-name">
                      <span className="asset-icon">BNB</span>
                      <span className="asset-label">BNB</span>
                    </td>
                    <td className="text-right">
                      {formatNumber(parseFloat(bnbData.bnb_balance), 4)}
                    </td>
                    <td className="text-right">
                      {formatEUR(parseFloat(bnbData.bnb_balance_eur))}
                    </td>
                    <td className="text-right overview-fee-info">
                      Fees: {formatEUR(parseFloat(bnbData.cumulative_fee_eur))}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Overview;
