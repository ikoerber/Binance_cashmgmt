/**
 * BotDashboard - Bot Dashboard with Alpha Score, Dry-Run Controls, Signal History
 *
 * Hero: Large Alpha Score + 4 factor bars + regime badge + dry-run toggle
 * Middle: Signal history LineChart
 * Bottom: KPI cards (P&L, trades, win rate, backtest summary, regime, portfolio)
 *
 * No order-placing UI elements (DRY-05 frontend enforcement).
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import { useChartTheme } from '../hooks/useChartTheme';
import {
  getAlphaScore,
  getTrailingStops,
  getDryRunStatus,
  getDryRunPortfolio,
  getDryRunDecisions,
  toggleDryRun,
  resetDryRunPortfolio,
  getBacktestRuns,
} from '../api/client';
import { formatNumber, formatEUR, formatPct } from '../utils/formatters';
import './BotDashboard.css';

/**
 * Map factor score from [-5, +5] to percentage [0, 100] for bar display.
 * Center (0) = 50%.
 */
const scoreToBarPct = (score) => {
  const clamped = Math.max(-5, Math.min(5, score || 0));
  return ((clamped + 5) / 10) * 100;
};

/**
 * Custom dot renderer for signal markers on the chart.
 */
const SignalDot = (props) => {
  const { cx, cy, payload } = props;
  if (!payload || !payload.action) return null;
  if (payload.action === 'BUY') {
    return (
      <polygon
        points={`${cx},${cy - 8} ${cx - 6},${cy + 4} ${cx + 6},${cy + 4}`}
        fill="#16a34a"
        stroke="#fff"
        strokeWidth={1}
      />
    );
  }
  if (payload.action === 'SELL') {
    return (
      <polygon
        points={`${cx},${cy + 8} ${cx - 6},${cy - 4} ${cx + 6},${cy - 4}`}
        fill="#dc2626"
        stroke="#fff"
        strokeWidth={1}
      />
    );
  }
  return null;
};

const BotDashboard = () => {
  const { symbol } = useSymbol();
  const { userId } = useUser();
  const queryClient = useQueryClient();
  const chartTheme = useChartTheme();

  // Data fetching
  const { data: alphaScore } = useQuery({
    queryKey: ['alpha-score', symbol, userId],
    queryFn: () => getAlphaScore(userId, symbol),
    refetchInterval: 30000,
  });

  const { data: dryRunStatus } = useQuery({
    queryKey: ['dry-run-status', userId],
    queryFn: () => getDryRunStatus(userId),
    refetchInterval: 15000,
  });

  const { data: portfolio } = useQuery({
    queryKey: ['dry-run-portfolio', userId],
    queryFn: () => getDryRunPortfolio(userId),
    refetchInterval: 15000,
  });

  const { data: decisionsData } = useQuery({
    queryKey: ['dry-run-decisions', userId, symbol],
    queryFn: () => getDryRunDecisions(userId, { symbol, limit: 100 }),
    refetchInterval: 30000,
  });

  const { data: backtestRuns } = useQuery({
    queryKey: ['backtest-runs', userId],
    queryFn: () => getBacktestRuns(userId),
    staleTime: 60000,
  });

  const { data: trailingStops } = useQuery({
    queryKey: ['trailing-stops', userId],
    queryFn: () => getTrailingStops(userId),
    refetchInterval: 30000,
  });

  // Mutations
  const toggleMutation = useMutation({
    mutationFn: () => toggleDryRun(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dry-run-status'] });
      queryClient.invalidateQueries({ queryKey: ['dry-run-portfolio'] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => resetDryRunPortfolio(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dry-run-portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['dry-run-status'] });
      queryClient.invalidateQueries({ queryKey: ['dry-run-decisions'] });
    },
  });

  const handleReset = () => {
    if (window.confirm('Virtuelles Portfolio zuruecksetzen? Alle Dry-Run Trades und Positionen werden geloescht.')) {
      resetMutation.mutate();
    }
  };

  // Derived data
  const isDryRunActive = dryRunStatus?.is_active ?? false;
  const score = alphaScore?.score ?? null;
  const signal = alphaScore?.trade_signal ?? 'NEUTRAL';
  const quality = alphaScore?.quality ?? 'degraded';
  const regime = alphaScore?.regime ?? null;
  const threshold = alphaScore?.threshold ?? 3.0;
  const factors = alphaScore?.factors ?? [];

  // Factor display mapping
  const factorLabels = {
    zscore: 'Z-Score',
    z_score: 'Z-Score',
    leadlag: 'Lead-Lag',
    lead_lag: 'Lead-Lag',
    imbalance: 'Orderbook',
    orderbook: 'Orderbook',
    orderbook_imbalance: 'Orderbook',
    funding: 'Funding',
    funding_rate: 'Funding',
  };

  const getFactorDisplay = () => {
    if (Array.isArray(factors) && factors.length > 0) {
      return factors.map(f => ({
        name: factorLabels[f.name] || factorLabels[f.factor] || f.name || f.factor || 'Unknown',
        score: parseFloat(f.sub_score ?? 0),
        quality: f.quality ?? 'full',
      }));
    }
    // Fallback: try top-level factor scores
    const result = [];
    if (alphaScore?.zscore_score != null) result.push({ name: 'Z-Score', score: alphaScore.zscore_score, quality: 'full' });
    if (alphaScore?.leadlag_score != null) result.push({ name: 'Lead-Lag', score: alphaScore.leadlag_score, quality: 'full' });
    if (alphaScore?.imbalance_score != null) result.push({ name: 'Orderbook', score: alphaScore.imbalance_score, quality: 'full' });
    if (alphaScore?.funding_score != null) result.push({ name: 'Funding', score: alphaScore.funding_score, quality: 'full' });
    return result;
  };

  const factorDisplay = getFactorDisplay();

  // Signal color
  const getSignalColor = (sig) => {
    if (sig === 'LONG') return '#16a34a';
    if (sig === 'SHORT') return '#dc2626';
    return '#64748b';
  };

  // Regime badge
  const getRegimeBadge = () => {
    if (!regime) return null;
    const label = regime.label ?? regime.regime ?? regime;
    const hurst = regime.hurst ?? regime.hurst_exponent ?? null;
    const labelStr = typeof label === 'string' ? label.toLowerCase() : '';

    let color = '#64748b'; // slate (transitional)
    let text = 'Transitional';
    if (labelStr.includes('trend')) {
      color = '#d97706'; // amber
      text = 'Trending';
    } else if (labelStr.includes('revert') || labelStr.includes('mean')) {
      color = '#3b82f6'; // blue
      text = 'Mean-Reverting';
    }

    const hurstStr = hurst != null ? ` (H: ${parseFloat(hurst).toFixed(2)})` : '';
    return { color, text: `${text}${hurstStr}` };
  };

  const regimeBadge = getRegimeBadge();

  // Chart data from decisions
  const decisions = decisionsData?.decisions ?? [];
  const chartData = [...decisions]
    .reverse()
    .map(d => ({
      time: new Date(d.evaluated_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }),
      alpha_score: d.alpha_score ?? 0,
      action: d.action,
      fullTime: d.evaluated_at,
    }));

  // Latest backtest (unwrap envelope: API returns { runs: [...], count })
  const runs = backtestRuns?.runs ?? [];
  const latestBacktest = runs.length > 0 ? runs[0] : null;

  // Virtual P&L
  const realizedPnl = parseFloat(portfolio?.realized_pnl ?? 0);
  const unrealizedPnl = parseFloat(portfolio?.unrealized_pnl ?? 0);
  const totalPnl = realizedPnl + unrealizedPnl;
  const tradeCount = portfolio?.trade_count ?? 0;
  const winRate = portfolio?.win_rate ?? null;
  const cash = parseFloat(portfolio?.cash ?? 0);
  const totalEquity = parseFloat(portfolio?.total_equity ?? 0);

  return (
    <div className="bot-container">
      {/* Dry-Run Banner */}
      {isDryRunActive && (
        <div className="bot-dry-run-banner">
          DRY-RUN MODE -- Keine echten Orders. Alle Trades sind virtuell.
        </div>
      )}

      {/* Hero Section */}
      <div className="bot-hero">
        <div className="bot-hero-left">
          <div className="bot-score-display">
            <span className="bot-score-label">Alpha Score</span>
            <span
              className="bot-score-value"
              style={{ color: getSignalColor(signal) }}
            >
              {score != null ? parseFloat(score).toFixed(2) : '--'}
            </span>
            <span
              className="bot-signal-badge"
              style={{ background: getSignalColor(signal) }}
            >
              {signal}
            </span>
          </div>

          {/* Quality Badge */}
          <span className={`bot-quality-badge quality-${quality}`}>
            {quality === 'full' ? 'Vollstaendig' : quality === 'partial' ? 'Teilweise' : 'Eingeschraenkt'}
          </span>

          {/* Regime Badge */}
          {regimeBadge && (
            <span
              className="bot-regime-badge"
              style={{ background: regimeBadge.color }}
              title={regimeBadge.text}
            >
              {regimeBadge.text}
            </span>
          )}
        </div>

        <div className="bot-hero-right">
          <button
            className={`bot-dry-run-toggle ${isDryRunActive ? 'active' : ''}`}
            onClick={() => toggleMutation.mutate()}
            disabled={toggleMutation.isPending}
          >
            {toggleMutation.isPending
              ? 'Wird umgeschaltet...'
              : isDryRunActive
                ? 'Dry-Run Stoppen'
                : 'Dry-Run Starten'}
          </button>
          {isDryRunActive && (
            <button
              className="bot-reset-btn"
              onClick={handleReset}
              disabled={resetMutation.isPending}
            >
              {resetMutation.isPending ? 'Reset...' : 'Portfolio Reset'}
            </button>
          )}
        </div>
      </div>

      {/* Factor Bars */}
      {factorDisplay.length > 0 && (
        <div className="bot-factor-bars">
          {factorDisplay.map((f, i) => {
            const pct = scoreToBarPct(f.score);
            const isPositive = f.score > 0;
            const isNeutral = Math.abs(f.score) < 0.01;
            return (
              <div key={i} className="bot-factor-bar">
                <span className="bot-factor-label">{f.name}</span>
                <div className="bot-factor-bar-track">
                  <div className="bot-factor-bar-center" />
                  {!isNeutral && (
                    <div
                      className={`bot-factor-bar-fill ${isPositive ? 'positive' : 'negative'}`}
                      style={isPositive
                        ? { left: '50%', width: `${pct - 50}%` }
                        : { left: `${pct}%`, width: `${50 - pct}%` }
                      }
                    />
                  )}
                </div>
                <span className={`bot-factor-score ${isPositive ? 'positive' : f.score < 0 ? 'negative' : ''}`}>
                  {parseFloat(f.score).toFixed(2)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Signal History Chart */}
      <div className="bot-signal-chart">
        <h3>Signal-Verlauf</h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.borderLight} />
              <XAxis
                dataKey="time"
                tick={{ fill: chartTheme.textMuted, fontSize: 11 }}
                stroke={chartTheme.border}
              />
              <YAxis
                domain={[-5, 5]}
                tick={{ fill: chartTheme.textMuted, fontSize: 11 }}
                stroke={chartTheme.border}
              />
              <Tooltip
                contentStyle={{
                  background: chartTheme.bgCard,
                  border: `1px solid ${chartTheme.border}`,
                  color: chartTheme.textPrimary,
                  borderRadius: 8,
                }}
                formatter={(value) => [parseFloat(value).toFixed(2), 'Alpha Score']}
              />
              <ReferenceLine y={threshold} stroke={chartTheme.textMuted} strokeDasharray="5 5" label="" />
              <ReferenceLine y={-threshold} stroke={chartTheme.textMuted} strokeDasharray="5 5" label="" />
              <ReferenceLine y={0} stroke={chartTheme.textMuted} strokeWidth={1} />
              <Line
                type="monotone"
                dataKey="alpha_score"
                stroke="#6366f1"
                strokeWidth={2}
                dot={<SignalDot />}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="bot-placeholder">
            Noch keine Signale aufgezeichnet. Aktiviere den Dry-Run Modus um Signale zu erfassen.
          </div>
        )}
      </div>

      {/* KPI Cards */}
      <div className="bot-kpi-grid">
        {/* Row 1 */}
        <div className="bot-kpi-card">
          <span className="bot-kpi-label">Virtueller P&L</span>
          <span className={`bot-kpi-value ${totalPnl >= 0 ? 'profit' : 'loss'}`}>
            {formatEUR(totalPnl)}
          </span>
          <span className="bot-kpi-sub">
            Real: {formatEUR(realizedPnl)} / Unreal: {formatEUR(unrealizedPnl)}
          </span>
        </div>

        <div className="bot-kpi-card">
          <span className="bot-kpi-label">Trades</span>
          <span className="bot-kpi-value">{tradeCount}</span>
        </div>

        <div className="bot-kpi-card">
          <span className="bot-kpi-label">Win Rate</span>
          <span className="bot-kpi-value">
            {winRate != null ? formatPct(parseFloat(winRate)) : '--'}
          </span>
        </div>

        {/* Row 2 */}
        <div className="bot-kpi-card bot-backtest-summary">
          <span className="bot-kpi-label">Letzter Backtest</span>
          {latestBacktest ? (
            <div className="bot-backtest-metrics">
              <div className="bot-backtest-metric">
                <span className="bot-backtest-metric-label">Return</span>
                <span className={`bot-backtest-metric-value ${parseFloat(latestBacktest.net_return_pct ?? 0) >= 0 ? 'profit' : 'loss'}`}>
                  {formatPct(parseFloat(latestBacktest.net_return_pct ?? 0))}
                </span>
              </div>
              <div className="bot-backtest-metric">
                <span className="bot-backtest-metric-label">Sharpe</span>
                <span className="bot-backtest-metric-value">
                  {formatNumber(latestBacktest.sharpe_ratio ?? 0, 2)}
                </span>
              </div>
              <div className="bot-backtest-metric">
                <span className="bot-backtest-metric-label">Trades</span>
                <span className="bot-backtest-metric-value">
                  {latestBacktest.trade_count ?? 0}
                </span>
              </div>
              <div className="bot-backtest-metric">
                <span className="bot-backtest-metric-label">Win Rate</span>
                <span className="bot-backtest-metric-value">
                  {latestBacktest.win_rate != null ? formatPct(parseFloat(latestBacktest.win_rate)) : '--'}
                </span>
              </div>
            </div>
          ) : (
            <span className="bot-kpi-value bot-kpi-muted">Kein Backtest</span>
          )}
          <a href="/backtest" className="bot-backtest-link">Zum Backtest</a>
        </div>

        <div className="bot-kpi-card">
          <span className="bot-kpi-label">Regime</span>
          {regimeBadge ? (
            <span
              className="bot-regime-badge bot-regime-badge-kpi"
              style={{ background: regimeBadge.color }}
            >
              {regimeBadge.text}
            </span>
          ) : (
            <span className="bot-kpi-value bot-kpi-muted">--</span>
          )}
        </div>

        <div className="bot-kpi-card">
          <span className="bot-kpi-label">Portfolio</span>
          <div className="bot-portfolio-display">
            <div className="bot-portfolio-row">
              <span>Cash:</span>
              <span>{formatEUR(cash)}</span>
            </div>
            <div className="bot-portfolio-row">
              <span>Equity:</span>
              <span className="bot-kpi-value">{formatEUR(totalEquity)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Trailing Stops */}
      {trailingStops?.stops && Object.keys(trailingStops.stops).length > 0 && (
        <div className="bot-trailing-stops">
          <h3>Trailing Stops</h3>
          <div className="bot-trailing-stops-grid">
            {Object.entries(trailingStops.stops).map(([sym, stop]) => (
              <div key={sym} className={`bot-trailing-stop-card ${stop.frozen ? 'frozen' : ''}`}>
                <div className="bot-trailing-stop-header">
                  <span className="bot-trailing-stop-symbol">{sym}</span>
                  {stop.frozen && (
                    <span className="bot-trailing-stop-frozen-badge">
                      FROZEN {stop.data_points_needed > 0 && `(${stop.data_points_needed} Punkte fehlen)`}
                    </span>
                  )}
                  {!stop.frozen && stop.direction && (
                    <span className={`bot-trailing-stop-direction ${stop.direction === 'LONG' ? 'long' : 'short'}`}>
                      {stop.direction}
                    </span>
                  )}
                </div>
                <div className="bot-trailing-stop-body">
                  <div className="bot-trailing-stop-row">
                    <span>Stop-Level</span>
                    <span className="bot-trailing-stop-value">
                      {stop.stop_level != null ? formatNumber(parseFloat(stop.stop_level), sym === 'BTCEUR' ? 2 : 4) : '--'}
                    </span>
                  </div>
                  <div className="bot-trailing-stop-row">
                    <span>ATR-Distanz</span>
                    <span className="bot-trailing-stop-value">
                      {stop.atr_distance != null ? formatNumber(parseFloat(stop.atr_distance), sym === 'BTCEUR' ? 2 : 4) : '--'}
                    </span>
                  </div>
                  <div className="bot-trailing-stop-row">
                    <span>Letzter Preis</span>
                    <span className="bot-trailing-stop-value">
                      {stop.last_price != null ? formatNumber(parseFloat(stop.last_price), sym === 'BTCEUR' ? 2 : 4) : '--'}
                    </span>
                  </div>
                  {stop.last_updated && (
                    <div className="bot-trailing-stop-updated">
                      Aktualisiert: {new Date(stop.last_updated).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default BotDashboard;
