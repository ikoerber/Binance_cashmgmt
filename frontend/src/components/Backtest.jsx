/**
 * Backtest - Alpha Backtest Page
 *
 * Standalone page for running historical Alpha Score signal simulations.
 * Displays equity curve with HODL benchmark, drawdown chart, monthly returns heatmap,
 * P&L histogram, trade list, and backtest history.
 */
import { useState, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ReferenceArea, Cell,
} from 'recharts';
import {
  runBacktest, getBacktestRuns, getBacktestRunDetail,
  runBacktestSweep, cancelBacktest, getBacktestSweepCsvUrl,
} from '../api/client';
import { formatNumber, formatEUR, formatDate, formatPct } from '../utils/formatters';
import { useChartTheme } from '../hooks/useChartTheme';
import { useUser } from '../contexts/UserContext';
import { useWebSocket } from '../contexts/WebSocketContext';
import useNotification from '../hooks/useNotification';
import './Backtest.css';

// ─── Constants ───

const SYMBOLS = [
  { value: 'BTCEUR', label: 'BTC/EUR' },
  { value: 'XRPEUR', label: 'XRP/EUR' },
];

const DEFAULT_ATR_MULT = { BTCEUR: '2.0', XRPEUR: '3.0' };

// ─── Helpers ───

const formatTimestamp = (ts) => {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' });
};

const formatTimestampFull = (ts) => {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
};

const bucketizeTrades = (trades) => {
  if (!trades || trades.length === 0) return [];
  const buckets = {};
  const step = 5;
  trades.forEach(t => {
    const pnl = parseFloat(t.pnl_pct) || 0;
    const bucketKey = Math.floor(pnl / step) * step;
    const label = `${bucketKey}%`;
    if (!buckets[label]) {
      buckets[label] = { label, sortKey: bucketKey, count: 0, isPositive: bucketKey >= 0 };
    }
    buckets[label].count += 1;
  });
  return Object.values(buckets).sort((a, b) => a.sortKey - b.sortKey);
};

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

const getHeatmapColor = (val) => {
  if (val === null || val === undefined) return 'var(--color-bg-subtle)';
  const v = parseFloat(val);
  if (v > 10) return 'var(--color-heatmap-strong-green, #166534)';
  if (v > 5) return 'var(--color-heatmap-green, #16a34a)';
  if (v > 1) return 'var(--color-heatmap-light-green, #86efac)';
  if (v > -1) return 'var(--color-bg-muted)';
  if (v > -5) return 'var(--color-heatmap-light-red, #fca5a5)';
  if (v > -10) return 'var(--color-heatmap-red, #dc2626)';
  return 'var(--color-heatmap-strong-red, #991b1b)';
};

const getHeatmapTextColor = (val) => {
  if (val === null || val === undefined) return 'var(--color-text-muted)';
  const v = parseFloat(val);
  if (Math.abs(v) > 5) return '#ffffff';
  return 'var(--color-text-primary)';
};

// ─── Sweep Helpers ───

const SWEEP_PARAMS = [
  { key: 'zscore_window', label: 'Z-Score Lookback', defaultMin: 30, defaultMax: 90, defaultStep: 15, isInt: true },
  { key: 'entry_threshold', label: 'Entry-Schwelle', defaultMin: 2.0, defaultMax: 4.0, defaultStep: 0.5, isInt: false },
  { key: 'atr_multiplier', label: 'ATR Multiplikator', defaultMin: 1.5, defaultMax: 3.0, defaultStep: 0.5, isInt: false },
  { key: 'weight_zscore', label: 'Z-Score Gewicht', defaultMin: 30, defaultMax: 50, defaultStep: 10, isInt: true },
];

const computeCombinationCount = (sweepRanges) => {
  let count = 1;
  for (const param of SWEEP_PARAMS) {
    const range = sweepRanges[param.key];
    if (!range || !range.enabled) continue;
    const min = parseFloat(range.min);
    const max = parseFloat(range.max);
    const step = parseFloat(range.step);
    if (isNaN(min) || isNaN(max) || isNaN(step) || step <= 0 || min > max) continue;
    const steps = Math.floor((max - min) / step) + 1;
    count *= Math.max(1, steps);
  }
  return count;
};

const PHASE_LABELS = {
  fetching_data: 'Daten laden...',
  warming_up: 'Warmup...',
  simulating: 'Simuliere...',
  computing_metrics: 'Metriken berechnen...',
  sweep: 'Sweep',
  complete: 'Abgeschlossen',
  cancelled: 'Abgebrochen',
};

// ─── Component ───

const Backtest = () => {
  const { symbol: urlSymbol } = useParams();
  const navigate = useNavigate();
  const { userId } = useUser();
  const queryClient = useQueryClient();
  const theme = useChartTheme();
  const { message, showMessage, dismissMessage } = useNotification();

  // ─── Form State ───
  const [symbol, setSymbol] = useState(urlSymbol || 'BTCEUR');
  const [months, setMonths] = useState(12);
  const [initialCapital, setInitialCapital] = useState('10000');
  const [positionFraction, setPositionFraction] = useState('10');
  const [entryThreshold, setEntryThreshold] = useState('3.0');
  const [feeRate, setFeeRate] = useState('0.1');
  const [slippage, setSlippage] = useState('0.05');
  const [atrMultiplier, setAtrMultiplier] = useState('2.0');

  // ─── Result State ───
  const [currentResult, setCurrentResult] = useState(null);
  const [showTrades, setShowTrades] = useState(false);
  const [expandedRunId, setExpandedRunId] = useState(null);

  // ─── Sweep State ───
  const [sweepRanges, setSweepRanges] = useState(() => {
    const init = {};
    SWEEP_PARAMS.forEach(p => {
      init[p.key] = { enabled: true, min: String(p.defaultMin), max: String(p.defaultMax), step: String(p.defaultStep) };
    });
    return init;
  });
  const [sweepResult, setSweepResult] = useState(null);
  const [sweepSortKey, setSweepSortKey] = useState('sharpe_ratio');
  const [sweepSortDir, setSweepSortDir] = useState('desc');
  const [cancelling, setCancelling] = useState(false);

  // ─── WebSocket Progress ───
  const { backtestProgress } = useWebSocket();

  // Auto-set ATR multiplier on symbol change + navigate to new URL
  const handleSymbolChange = (newSymbol) => {
    setSymbol(newSymbol);
    setAtrMultiplier(DEFAULT_ATR_MULT[newSymbol] || '2.0');
    navigate(`/s/${newSymbol}/backtest`);
  };

  // ─── Queries ───
  const { data: runsData } = useQuery({
    queryKey: ['backtest-runs', userId],
    queryFn: () => getBacktestRuns(userId),
  });

  const { data: expandedRunData, isLoading: expandedRunLoading } = useQuery({
    queryKey: ['backtest-run-detail', userId, expandedRunId],
    queryFn: () => getBacktestRunDetail(userId, expandedRunId),
    enabled: !!expandedRunId,
    staleTime: Infinity,
  });

  // ─── Mutations ───
  const runMutation = useMutation({
    mutationFn: () => runBacktest(userId, {
      symbol,
      months,
      initial_capital: initialCapital,
      fee_rate: String(parseFloat(feeRate) / 100),
      slippage_pct: String(parseFloat(slippage) / 100),
      position_fraction: String(parseFloat(positionFraction) / 100),
      entry_threshold: entryThreshold,
      atr_multiplier: atrMultiplier,
    }),
    onSuccess: (data) => {
      setCurrentResult(data);
      queryClient.invalidateQueries({ queryKey: ['backtest-runs', userId] });
      showMessage('success', `Backtest abgeschlossen: ${data.metrics?.trade_count || 0} Trades simuliert.`);
    },
    onError: (err) => {
      showMessage('error', err.response?.data?.detail || err.message);
    },
  });

  // ─── Sweep Mutation ───
  const sweepMutation = useMutation({
    mutationFn: () => {
      const sweep = {};
      SWEEP_PARAMS.forEach(p => {
        const r = sweepRanges[p.key];
        if (r && r.enabled) {
          sweep[p.key] = {
            min: parseFloat(r.min),
            max: parseFloat(r.max),
            step: parseFloat(r.step),
          };
        }
      });
      return runBacktestSweep(userId, {
        symbol,
        months,
        initial_capital: initialCapital,
        fee_rate: String(parseFloat(feeRate) / 100),
        slippage_pct: String(parseFloat(slippage) / 100),
        position_fraction: String(parseFloat(positionFraction) / 100),
        sweep,
      });
    },
    onSuccess: (data) => {
      setSweepResult(data);
      queryClient.invalidateQueries({ queryKey: ['backtest-runs', userId] });
      const msg = data.cancelled
        ? `Sweep abgebrochen: ${data.completed_count}/${data.combination_count} Kombinationen.`
        : `Sweep abgeschlossen: ${data.completed_count} Kombinationen in ${data.duration_seconds}s.`;
      showMessage('success', msg);
    },
    onError: (err) => {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'object' && detail.error) {
        showMessage('error', `${detail.error} (${detail.combination_count} Kombinationen, max ${detail.max_allowed})`);
      } else {
        showMessage('error', detail || err.message);
      }
    },
  });

  const handleCancelBacktest = useCallback(async () => {
    const runId = backtestProgress?.run_id;
    if (!runId) return;
    setCancelling(true);
    try {
      await cancelBacktest(userId, runId);
    } catch {
      // Ignore — may have already finished
    }
    setCancelling(false);
  }, [userId, backtestProgress]);

  const handleSweepSort = useCallback((key) => {
    setSweepSortDir(prev => (sweepSortKey === key ? (prev === 'asc' ? 'desc' : 'asc') : 'desc'));
    setSweepSortKey(key);
  }, [sweepSortKey]);

  const handleSweepRangeChange = useCallback((paramKey, field, value) => {
    setSweepRanges(prev => ({
      ...prev,
      [paramKey]: { ...prev[paramKey], [field]: value },
    }));
  }, []);

  const handleSweepToggle = useCallback((paramKey) => {
    setSweepRanges(prev => ({
      ...prev,
      [paramKey]: { ...prev[paramKey], enabled: !prev[paramKey].enabled },
    }));
  }, []);

  // ─── Sweep Derived Data ───
  const combinationCount = useMemo(() => computeCombinationCount(sweepRanges), [sweepRanges]);
  const sweepBlocked = combinationCount > 500;
  const sweepWarning = combinationCount > 100 && !sweepBlocked;
  const hasEnabledSweepParam = SWEEP_PARAMS.some(p => sweepRanges[p.key]?.enabled);

  const sortedSweepResults = useMemo(() => {
    if (!sweepResult?.results) return [];
    return [...sweepResult.results].sort((a, b) => {
      const av = parseFloat(a[sweepSortKey]) || 0;
      const bv = parseFloat(b[sweepSortKey]) || 0;
      return sweepSortDir === 'asc' ? av - bv : bv - av;
    });
  }, [sweepResult, sweepSortKey, sweepSortDir]);

  const handleCsvExport = useCallback(() => {
    if (!sweepResult?.sweep_id) return;
    const url = getBacktestSweepCsvUrl(userId, sweepResult.sweep_id);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sweep_${sweepResult.sweep_id}.csv`;
    // Add API key header — use fetch+blob approach
    fetch(url, {
      headers: { 'X-API-Key': import.meta.env.VITE_API_KEY || '' },
    })
      .then(res => res.blob())
      .then(blob => {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `sweep_${sweepResult.sweep_id}.csv`;
        a.click();
        URL.revokeObjectURL(blobUrl);
      });
  }, [userId, sweepResult]);

  // ─── Progress State ───
  const isRunning = runMutation.isPending || sweepMutation.isPending;
  const showProgress = backtestProgress && backtestProgress.phase !== 'complete' && backtestProgress.phase !== 'cancelled';

  // ─── Derived Data ───
  const runs = runsData?.runs || [];
  const metrics = currentResult?.metrics;
  const benchmark = currentResult?.benchmark;
  const equityCurve = currentResult?.equity_curve || [];
  const warmupEndIndex = currentResult?.warmup_end_index || 0;

  const trades = useMemo(() => currentResult?.trades || [], [currentResult]);
  const monthlyReturns = useMemo(() => currentResult?.monthly_returns || [], [currentResult]);

  const tradeHistogram = useMemo(() => bucketizeTrades(trades), [trades]);

  // Monthly returns grouped by year
  const heatmapData = useMemo(() => {
    if (!monthlyReturns.length) return [];
    const byYear = {};
    monthlyReturns.forEach(mr => {
      if (!byYear[mr.year]) byYear[mr.year] = {};
      byYear[mr.year][mr.month] = mr.return_pct;
    });
    return Object.entries(byYear)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([year, months_data]) => ({ year, months: months_data }));
  }, [monthlyReturns]);

  // Warmup area bounds
  const warmupEnd = warmupEndIndex > 0 && equityCurve.length > warmupEndIndex
    ? equityCurve[warmupEndIndex]?.timestamp
    : null;

  // ─── Render ───

  return (
    <div className="backtest-container">
      {/* Header */}
      <div className="bt-header">
        <h2>Alpha Backtest</h2>
        <p>Historische Alpha Score Signalsimulation</p>
      </div>

      {/* Notification */}
      {message && (
        <div className={`bt-message bt-message-${message.type}`}>
          {message.text}
          <button className="bt-message-close" onClick={dismissMessage}>&times;</button>
        </div>
      )}

      {/* ─── Configuration Form ─── */}
      <div className="bt-form-section">
        <h3>Konfiguration</h3>
        <div className="bt-form-grid">
          <div className="bt-form-group">
            <label>Symbol</label>
            <select value={symbol} onChange={(e) => handleSymbolChange(e.target.value)}>
              {SYMBOLS.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          <div className="bt-form-group">
            <label>Zeitraum</label>
            <div className="bt-input-with-unit">
              <input
                type="number"
                value={months}
                onChange={(e) => setMonths(Math.min(24, Math.max(1, Number(e.target.value))))}
                min="1"
                max="24"
              />
              <span className="bt-unit">Monate</span>
            </div>
          </div>

          <div className="bt-form-group">
            <label>Startkapital</label>
            <div className="bt-input-with-unit">
              <input
                type="number"
                value={initialCapital}
                onChange={(e) => setInitialCapital(e.target.value)}
                min="100"
                step="1000"
              />
              <span className="bt-unit">EUR</span>
            </div>
          </div>

          <div className="bt-form-group">
            <label>Positionsgroesse</label>
            <div className="bt-input-with-unit">
              <input
                type="number"
                value={positionFraction}
                onChange={(e) => setPositionFraction(e.target.value)}
                min="1"
                max="100"
                step="1"
              />
              <span className="bt-unit">%</span>
            </div>
          </div>

          <div className="bt-form-group">
            <label>Entry-Schwelle</label>
            <div className="bt-input-with-unit">
              <input
                type="number"
                value={entryThreshold}
                onChange={(e) => setEntryThreshold(e.target.value)}
                min="0.5"
                max="5.0"
                step="0.1"
              />
              <span className="bt-unit">Score</span>
            </div>
          </div>

          <div className="bt-form-group">
            <label>Gebuehren</label>
            <div className="bt-input-with-unit">
              <input
                type="number"
                value={feeRate}
                onChange={(e) => setFeeRate(e.target.value)}
                min="0"
                max="1"
                step="0.01"
              />
              <span className="bt-unit">%</span>
            </div>
          </div>

          <div className="bt-form-group">
            <label>Slippage</label>
            <div className="bt-input-with-unit">
              <input
                type="number"
                value={slippage}
                onChange={(e) => setSlippage(e.target.value)}
                min="0"
                max="1"
                step="0.01"
              />
              <span className="bt-unit">%</span>
            </div>
          </div>

          <div className="bt-form-group">
            <label>ATR Multiplikator</label>
            <div className="bt-input-with-unit">
              <input
                type="number"
                value={atrMultiplier}
                onChange={(e) => setAtrMultiplier(e.target.value)}
                min="0.5"
                max="10"
                step="0.5"
              />
              <span className="bt-unit">x ATR</span>
            </div>
          </div>
        </div>

        <div className="bt-form-actions">
          <button
            className="btn-bt-run"
            onClick={() => runMutation.mutate()}
            disabled={isRunning}
          >
            {runMutation.isPending ? 'Simuliere...' : 'Backtest starten'}
          </button>
        </div>
      </div>

      {/* ─── Progress Bar ─── */}
      {(showProgress || backtestProgress?.phase === 'cancelled') && (
        <div className="bt-progress-section">
          <div className="bt-progress-header">
            <span className="bt-progress-phase">
              {backtestProgress?.phase === 'sweep'
                ? `Sweep ${backtestProgress.combination_current || 0} / ${backtestProgress.combination_total || 0}`
                : PHASE_LABELS[backtestProgress?.phase] || 'Verarbeite...'}
            </span>
            {backtestProgress?.elapsed_seconds != null && (
              <span className="bt-progress-elapsed">{backtestProgress.elapsed_seconds}s</span>
            )}
          </div>
          <div className="bt-progress-bar-track">
            <div
              className="bt-progress-bar-fill"
              style={{ width: `${Math.min(100, backtestProgress?.progress_pct || backtestProgress?.pct || 0)}%` }}
            />
          </div>
          <div className="bt-progress-details">
            {backtestProgress?.processed != null && (
              <span>{formatNumber(backtestProgress.processed, 0)} / {formatNumber(backtestProgress.total, 0)} Kerzen</span>
            )}
            {backtestProgress?.trades_found != null && (
              <span>{backtestProgress.trades_found} Trades gefunden</span>
            )}
            {backtestProgress?.phase === 'cancelled' && (
              <span className="bt-progress-cancelled-notice">Abgebrochen — Teilergebnisse anzeigen</span>
            )}
          </div>
          {isRunning && (
            <button
              className="btn-bt-cancel"
              onClick={handleCancelBacktest}
              disabled={cancelling}
            >
              {cancelling ? 'Abbrechen...' : 'Abbrechen'}
            </button>
          )}
        </div>
      )}

      {/* ─── Parameter Sweep ─── */}
      <div className="bt-form-section bt-sweep-section">
        <h3>Parameter Sweep</h3>
        <div className="bt-sweep-grid">
          {SWEEP_PARAMS.map(param => {
            const range = sweepRanges[param.key];
            return (
              <div key={param.key} className={`bt-sweep-row ${range?.enabled ? '' : 'bt-sweep-disabled'}`}>
                <label className="bt-sweep-toggle">
                  <input
                    type="checkbox"
                    checked={range?.enabled || false}
                    onChange={() => handleSweepToggle(param.key)}
                  />
                  <span>{param.label}</span>
                </label>
                <div className="bt-sweep-inputs">
                  <div className="bt-sweep-field">
                    <span className="bt-sweep-field-label">Min</span>
                    <input
                      type="number"
                      value={range?.min || ''}
                      onChange={(e) => handleSweepRangeChange(param.key, 'min', e.target.value)}
                      disabled={!range?.enabled}
                      step={param.isInt ? '1' : '0.1'}
                    />
                  </div>
                  <div className="bt-sweep-field">
                    <span className="bt-sweep-field-label">Max</span>
                    <input
                      type="number"
                      value={range?.max || ''}
                      onChange={(e) => handleSweepRangeChange(param.key, 'max', e.target.value)}
                      disabled={!range?.enabled}
                      step={param.isInt ? '1' : '0.1'}
                    />
                  </div>
                  <div className="bt-sweep-field">
                    <span className="bt-sweep-field-label">Step</span>
                    <input
                      type="number"
                      value={range?.step || ''}
                      onChange={(e) => handleSweepRangeChange(param.key, 'step', e.target.value)}
                      disabled={!range?.enabled}
                      step={param.isInt ? '1' : '0.1'}
                      min="0.1"
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="bt-sweep-footer">
          <span className={`bt-sweep-badge ${sweepBlocked ? 'bt-sweep-badge-error' : sweepWarning ? 'bt-sweep-badge-warning' : 'bt-sweep-badge-ok'}`}>
            {combinationCount} Kombination{combinationCount !== 1 ? 'en' : ''}
            {sweepBlocked && ' — Max 500 erlaubt'}
            {sweepWarning && ' — Kann mehrere Minuten dauern'}
          </span>
          <button
            className="btn-bt-run btn-bt-sweep"
            onClick={() => sweepMutation.mutate()}
            disabled={isRunning || sweepBlocked || !hasEnabledSweepParam}
          >
            {sweepMutation.isPending ? 'Sweep laeuft...' : 'Sweep starten'}
          </button>
        </div>
      </div>

      {/* ─── Sweep Results ─── */}
      {sweepResult && sweepResult.results?.length > 0 && (
        <div className="bt-sweep-results">
          <div className="bt-sweep-results-header">
            <h3>Sweep Ergebnisse ({sweepResult.results.length} Kombinationen)</h3>
            <button className="btn-bt-csv" onClick={handleCsvExport}>
              CSV Export
            </button>
          </div>
          {sweepResult.cancelled && (
            <div className="bt-sweep-cancelled-notice">
              Sweep abgebrochen — {sweepResult.completed_count} von {sweepResult.combination_count} Kombinationen abgeschlossen
            </div>
          )}
          <div className="bt-table-container bt-sweep-table-container">
            <table className="bt-table bt-sweep-table">
              <thead>
                <tr>
                  {SWEEP_PARAMS.filter(p => sweepRanges[p.key]?.enabled).map(p => (
                    <th key={p.key} className="bt-sortable" onClick={() => handleSweepSort(p.key)}>
                      {p.label}
                      {sweepSortKey === p.key && (
                        <span className="bt-sort-arrow">{sweepSortDir === 'asc' ? ' \u25B2' : ' \u25BC'}</span>
                      )}
                    </th>
                  ))}
                  <th className="bt-sortable" onClick={() => handleSweepSort('net_return_pct')}>
                    Rendite %{sweepSortKey === 'net_return_pct' && <span className="bt-sort-arrow">{sweepSortDir === 'asc' ? ' \u25B2' : ' \u25BC'}</span>}
                  </th>
                  <th className="bt-sortable" onClick={() => handleSweepSort('sharpe_ratio')}>
                    Sharpe{sweepSortKey === 'sharpe_ratio' && <span className="bt-sort-arrow">{sweepSortDir === 'asc' ? ' \u25B2' : ' \u25BC'}</span>}
                  </th>
                  <th className="bt-sortable" onClick={() => handleSweepSort('max_drawdown_pct')}>
                    Max DD %{sweepSortKey === 'max_drawdown_pct' && <span className="bt-sort-arrow">{sweepSortDir === 'asc' ? ' \u25B2' : ' \u25BC'}</span>}
                  </th>
                  <th className="bt-sortable" onClick={() => handleSweepSort('trade_count')}>
                    Trades{sweepSortKey === 'trade_count' && <span className="bt-sort-arrow">{sweepSortDir === 'asc' ? ' \u25B2' : ' \u25BC'}</span>}
                  </th>
                  <th className="bt-sortable" onClick={() => handleSweepSort('win_rate')}>
                    Win %{sweepSortKey === 'win_rate' && <span className="bt-sort-arrow">{sweepSortDir === 'asc' ? ' \u25B2' : ' \u25BC'}</span>}
                  </th>
                  <th>Fees</th>
                  <th>Slippage</th>
                </tr>
              </thead>
              <tbody>
                {sortedSweepResults.map((row, idx) => {
                  const ret = parseFloat(row.net_return_pct) || 0;
                  const sharpe = parseFloat(row.sharpe_ratio) || 0;
                  const dd = parseFloat(row.max_drawdown_pct) || 0;
                  return (
                    <tr key={idx}>
                      {SWEEP_PARAMS.filter(p => sweepRanges[p.key]?.enabled).map(p => (
                        <td key={p.key} className="cell-mono">{row[p.key] ?? '-'}</td>
                      ))}
                      <td className={`cell-mono ${ret >= 0 ? 'bt-profit' : 'bt-loss'}`}>
                        {formatPct(ret)}
                      </td>
                      <td className={`cell-mono ${sharpe >= 1 ? 'bt-profit' : ''}`}>
                        {formatNumber(sharpe, 2)}
                      </td>
                      <td className="cell-mono bt-loss">
                        {formatPct(dd)}
                      </td>
                      <td className="cell-mono">{row.trade_count ?? 0}</td>
                      <td className="cell-mono">
                        {row.win_rate != null ? `${formatNumber(parseFloat(row.win_rate) * 100, 1)}%` : '-'}
                      </td>
                      <td className="cell-mono">{row.total_fees != null ? formatEUR(parseFloat(row.total_fees)) : '-'}</td>
                      <td className="cell-mono">{row.total_slippage != null ? formatEUR(parseFloat(row.total_slippage)) : '-'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── Results Section ─── */}
      {currentResult && (
        <div className="bt-results">
          {/* C1: Metrics Cards */}
          <div className="bt-metrics-grid">
            <div className={`bt-metric-card ${parseFloat(metrics?.net_return_pct) >= 0 ? 'bt-metric-positive' : 'bt-metric-negative'}`}>
              <span className="bt-metric-label">Netto-Rendite</span>
              <span className="bt-metric-value">
                {metrics?.net_return_pct != null ? formatPct(parseFloat(metrics.net_return_pct)) : 'N/A'}
              </span>
            </div>
            <div className="bt-metric-card">
              <span className="bt-metric-label">Sharpe Ratio</span>
              <span className="bt-metric-value">
                {metrics?.sharpe_ratio != null ? formatNumber(parseFloat(metrics.sharpe_ratio), 2) : 'N/A'}
              </span>
            </div>
            <div className="bt-metric-card bt-metric-negative">
              <span className="bt-metric-label">Max Drawdown</span>
              <span className="bt-metric-value">
                {metrics?.max_drawdown_pct != null ? formatPct(parseFloat(metrics.max_drawdown_pct)) : 'N/A'}
              </span>
            </div>
            <div className="bt-metric-card">
              <span className="bt-metric-label">Trades</span>
              <span className="bt-metric-value">{metrics?.trade_count ?? 'N/A'}</span>
            </div>
            <div className="bt-metric-card">
              <span className="bt-metric-label">Win Rate</span>
              <span className="bt-metric-value">
                {metrics?.win_rate != null && metrics.trade_count > 0
                  ? `${formatNumber(parseFloat(metrics.win_rate) * 100, 1)}%`
                  : 'N/A'}
              </span>
            </div>
            <div className={`bt-metric-card ${parseFloat(metrics?.net_return_pct) - parseFloat(benchmark?.return_pct || 0) >= 0 ? 'bt-metric-positive' : 'bt-metric-negative'}`}>
              <span className="bt-metric-label">Excess Return</span>
              <span className="bt-metric-value">
                {currentResult?.excess_return_pct != null
                  ? formatPct(parseFloat(currentResult.excess_return_pct))
                  : benchmark?.return_pct != null && metrics?.net_return_pct != null
                    ? formatPct(parseFloat(metrics.net_return_pct) - parseFloat(benchmark.return_pct))
                    : 'N/A'}
              </span>
            </div>
          </div>

          {/* Second metrics row: cost details */}
          <div className="bt-metrics-grid bt-metrics-secondary">
            <div className="bt-metric-card bt-metric-small">
              <span className="bt-metric-label">Gebuehren gesamt</span>
              <span className="bt-metric-value">
                {metrics?.total_fees != null ? formatEUR(parseFloat(metrics.total_fees)) : 'N/A'}
              </span>
            </div>
            <div className="bt-metric-card bt-metric-small">
              <span className="bt-metric-label">Slippage gesamt</span>
              <span className="bt-metric-value">
                {metrics?.total_slippage != null ? formatEUR(parseFloat(metrics.total_slippage)) : 'N/A'}
              </span>
            </div>
            <div className="bt-metric-card bt-metric-small">
              <span className="bt-metric-label">Benchmark-Rendite</span>
              <span className="bt-metric-value">
                {benchmark?.return_pct != null ? formatPct(parseFloat(benchmark.return_pct)) : 'N/A'}
              </span>
            </div>
            <div className="bt-metric-card bt-metric-small">
              <span className="bt-metric-label">Avg Trade Dauer</span>
              <span className="bt-metric-value">
                {metrics?.avg_trade_duration != null ? `${metrics.avg_trade_duration} Kerzen` : 'N/A'}
              </span>
            </div>
          </div>

          {/* C2: Equity Curve Chart */}
          {equityCurve.length > 0 && (
            <div className="bt-chart-section">
              <h3>Equity Curve</h3>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={equityCurve} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={theme.borderLight} />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={formatTimestamp}
                    stroke={theme.textMuted}
                    fontSize={11}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    stroke={theme.textMuted}
                    fontSize={11}
                    tickFormatter={(v) => `${formatNumber(v, 0)}`}
                  />
                  <Tooltip
                    contentStyle={{
                      background: theme.bgCard,
                      border: `1px solid ${theme.border}`,
                      borderRadius: '8px',
                      color: theme.textPrimary,
                    }}
                    labelFormatter={formatTimestampFull}
                    formatter={(value, name) => [
                      `${formatNumber(parseFloat(value), 2)} EUR`,
                      name === 'equity' ? 'Strategie' : 'HODL Benchmark',
                    ]}
                  />
                  <Legend
                    formatter={(value) => value === 'equity' ? 'Strategie' : 'HODL Benchmark (50/50 BTC/XRP)'}
                  />
                  {warmupEnd && (
                    <ReferenceArea
                      x1={equityCurve[0]?.timestamp}
                      x2={warmupEnd}
                      fill={theme.textMuted}
                      fillOpacity={0.15}
                      label={{ value: 'Warmup', position: 'insideTop', fill: theme.textMuted, fontSize: 11 }}
                    />
                  )}
                  <Line
                    type="monotone"
                    dataKey="equity"
                    stroke={theme.chart1}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: theme.chart1 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="benchmark_equity"
                    stroke={theme.textMuted}
                    strokeWidth={1.5}
                    strokeDasharray="6 3"
                    dot={false}
                    activeDot={{ r: 3, fill: theme.textMuted }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* C3: Drawdown Chart */}
          {equityCurve.length > 0 && (
            <div className="bt-chart-section bt-chart-drawdown">
              <h3>Drawdown</h3>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={equityCurve} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={theme.borderLight} />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={formatTimestamp}
                    stroke={theme.textMuted}
                    fontSize={11}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    stroke={theme.textMuted}
                    fontSize={11}
                    tickFormatter={(v) => `${formatNumber(v, 1)}%`}
                    domain={['dataMin', 0]}
                  />
                  <Tooltip
                    contentStyle={{
                      background: theme.bgCard,
                      border: `1px solid ${theme.border}`,
                      borderRadius: '8px',
                      color: theme.textPrimary,
                    }}
                    labelFormatter={formatTimestampFull}
                    formatter={(value) => [`${formatNumber(parseFloat(value), 2)}%`, 'Drawdown']}
                  />
                  <Area
                    type="monotone"
                    dataKey="drawdown_pct"
                    stroke={theme.loss}
                    fill={theme.loss}
                    fillOpacity={0.2}
                    strokeWidth={1.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* C4: Monthly Returns Heatmap */}
          {heatmapData.length > 0 && (
            <div className="bt-chart-section bt-heatmap-section">
              <h3>Monatliche Renditen</h3>
              <div className="bt-heatmap">
                <div className="bt-heatmap-header">
                  <div className="bt-heatmap-year-label" />
                  {MONTH_LABELS.map(m => (
                    <div key={m} className="bt-heatmap-month-label">{m}</div>
                  ))}
                </div>
                {heatmapData.map(row => (
                  <div key={row.year} className="bt-heatmap-row">
                    <div className="bt-heatmap-year-label">{row.year}</div>
                    {MONTH_LABELS.map((_, i) => {
                      const val = row.months[i + 1];
                      return (
                        <div
                          key={i}
                          className="bt-heatmap-cell"
                          style={{
                            backgroundColor: getHeatmapColor(val),
                            color: getHeatmapTextColor(val),
                          }}
                          title={val != null ? `${formatNumber(parseFloat(val), 1)}%` : '-'}
                        >
                          {val != null ? `${formatNumber(parseFloat(val), 1)}%` : ''}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* C5: Trade Distribution Histogram */}
          {tradeHistogram.length > 0 && (
            <div className="bt-chart-section">
              <h3>Trade P&L Verteilung</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={tradeHistogram} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={theme.borderLight} />
                  <XAxis dataKey="label" stroke={theme.textMuted} fontSize={11} />
                  <YAxis stroke={theme.textMuted} fontSize={11} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      background: theme.bgCard,
                      border: `1px solid ${theme.border}`,
                      borderRadius: '8px',
                      color: theme.textPrimary,
                    }}
                    formatter={(value) => [value, 'Trades']}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {tradeHistogram.map((entry, index) => (
                      <Cell key={index} fill={entry.isPositive ? theme.profit : theme.loss} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* C6: Trade List (collapsible) */}
          {trades.length > 0 && (
            <div className="bt-trades-section">
              <button
                className="btn-bt-trades-toggle"
                onClick={() => setShowTrades(v => !v)}
              >
                {showTrades ? 'Trades ausblenden' : `Trades anzeigen (${trades.length})`}
              </button>
              {showTrades && (
                <div className="bt-table-container">
                  <table className="bt-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>Entry-Preis</th>
                        <th>Exit-Preis</th>
                        <th>Menge</th>
                        <th>P&L (EUR)</th>
                        <th>P&L (%)</th>
                        <th>Dauer</th>
                        <th>Alpha Score</th>
                        <th>Gebuehren</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...trades].sort((a, b) => {
                        const ta = a.entry_time || '';
                        const tb = b.entry_time || '';
                        return tb.localeCompare(ta);
                      }).map((trade, idx) => (
                        <tr key={idx} className={trade.is_open ? 'bt-trade-open' : ''}>
                          <td>{trades.length - idx}</td>
                          <td className="cell-mono">{formatTimestampFull(trade.entry_time)}</td>
                          <td className="cell-mono">
                            {trade.is_open
                              ? <span className="bt-badge bt-badge-open">OPEN</span>
                              : formatTimestampFull(trade.exit_time)}
                          </td>
                          <td className="cell-mono">{formatNumber(parseFloat(trade.entry_price), 2)}</td>
                          <td className="cell-mono">
                            {trade.is_open ? '-' : formatNumber(parseFloat(trade.exit_price), 2)}
                          </td>
                          <td className="cell-mono">{formatNumber(parseFloat(trade.qty), 8)}</td>
                          <td className={`cell-mono ${parseFloat(trade.pnl_eur) >= 0 ? 'bt-profit' : 'bt-loss'}`}>
                            {trade.is_open ? '-' : formatEUR(parseFloat(trade.pnl_eur))}
                          </td>
                          <td className={`cell-mono ${parseFloat(trade.pnl_pct) >= 0 ? 'bt-profit' : 'bt-loss'}`}>
                            {trade.is_open ? '-' : formatPct(parseFloat(trade.pnl_pct))}
                          </td>
                          <td>{trade.duration_candles != null ? `${trade.duration_candles}` : '-'}</td>
                          <td className="cell-mono">
                            {trade.alpha_score_at_entry != null
                              ? formatNumber(parseFloat(trade.alpha_score_at_entry), 2)
                              : '-'}
                          </td>
                          <td className="cell-mono">
                            {trade.fees_paid != null ? formatEUR(parseFloat(trade.fees_paid)) : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ─── Backtest History ─── */}
      <div className="bt-history-section">
        <h3>Vorherige Runs</h3>
        {runs.length === 0 ? (
          <div className="bt-history-empty">
            Noch keine Backtests. Konfiguriere und starte einen oben.
          </div>
        ) : (
          <div className="bt-history-list">
            {runs.map(run => {
              const isExpanded = expandedRunId === run.id;
              const netReturn = parseFloat(run.net_return_pct);
              const isPositive = netReturn >= 0;
              return (
                <div key={run.id} className={`bt-run-card ${isExpanded ? 'bt-run-expanded' : ''}`}>
                  <div
                    className="bt-run-header"
                    onClick={() => setExpandedRunId(isExpanded ? null : run.id)}
                  >
                    <div className="bt-run-info">
                      <span className="bt-run-date">{formatDate(run.created_at)}</span>
                      <span className="bt-run-symbol">{run.symbol}</span>
                      <span className="bt-run-period">
                        {run.candle_count} Kerzen
                      </span>
                    </div>
                    <div className="bt-run-metrics">
                      <span className={`bt-run-return ${isPositive ? 'bt-profit' : 'bt-loss'}`}>
                        {formatPct(netReturn)}
                      </span>
                      <span className="bt-run-detail">
                        Sharpe: {run.sharpe_ratio != null ? formatNumber(parseFloat(run.sharpe_ratio), 2) : 'N/A'}
                      </span>
                      <span className="bt-run-detail">
                        {run.trade_count} Trades
                      </span>
                      {run.benchmark_return_pct != null && (
                        <span className={`bt-run-detail ${parseFloat(run.excess_return_pct) >= 0 ? 'bt-profit' : 'bt-loss'}`}>
                          vs BM: {formatPct(parseFloat(run.excess_return_pct || (netReturn - parseFloat(run.benchmark_return_pct))))}
                        </span>
                      )}
                    </div>
                    <span className="bt-run-expand-icon">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                  </div>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="bt-run-body">
                      {expandedRunLoading ? (
                        <div className="bt-run-loading">Lade Details...</div>
                      ) : expandedRunData ? (
                        <>
                          {/* Mini equity curve */}
                          {expandedRunData.equity_curve?.length > 0 && (
                            <div className="bt-run-chart">
                              <ResponsiveContainer width="100%" height={200}>
                                <LineChart data={expandedRunData.equity_curve}>
                                  <CartesianGrid strokeDasharray="3 3" stroke={theme.borderLight} />
                                  <XAxis
                                    dataKey="timestamp"
                                    tickFormatter={formatTimestamp}
                                    stroke={theme.textMuted}
                                    fontSize={10}
                                    interval="preserveStartEnd"
                                  />
                                  <YAxis stroke={theme.textMuted} fontSize={10} />
                                  <Tooltip
                                    contentStyle={{
                                      background: theme.bgCard,
                                      border: `1px solid ${theme.border}`,
                                      borderRadius: '8px',
                                      color: theme.textPrimary,
                                      fontSize: '12px',
                                    }}
                                    labelFormatter={formatTimestampFull}
                                    formatter={(value, name) => [
                                      `${formatNumber(parseFloat(value), 2)} EUR`,
                                      name === 'equity' ? 'Strategie' : 'Benchmark',
                                    ]}
                                  />
                                  <Line type="monotone" dataKey="equity" stroke={theme.chart1} strokeWidth={2} dot={false} />
                                  <Line type="monotone" dataKey="benchmark_equity" stroke={theme.textMuted} strokeWidth={1} strokeDasharray="4 2" dot={false} />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          )}

                          {/* Mini trade list */}
                          {expandedRunData.trades?.length > 0 && (
                            <div className="bt-run-trades">
                              <span className="bt-run-trades-count">
                                {expandedRunData.trades.length} Trades
                              </span>
                              <div className="bt-table-container bt-run-trades-table">
                                <table className="bt-table bt-table-compact">
                                  <thead>
                                    <tr>
                                      <th>Entry</th>
                                      <th>Exit</th>
                                      <th>P&L</th>
                                      <th>P&L %</th>
                                      <th>Dauer</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {expandedRunData.trades.slice(0, 20).map((t, i) => (
                                      <tr key={i}>
                                        <td className="cell-mono">{formatTimestamp(t.entry_time)}</td>
                                        <td className="cell-mono">
                                          {t.is_open
                                            ? <span className="bt-badge bt-badge-open">OPEN</span>
                                            : formatTimestamp(t.exit_time)}
                                        </td>
                                        <td className={`cell-mono ${parseFloat(t.pnl_eur) >= 0 ? 'bt-profit' : 'bt-loss'}`}>
                                          {t.is_open ? '-' : formatEUR(parseFloat(t.pnl_eur))}
                                        </td>
                                        <td className={`cell-mono ${parseFloat(t.pnl_pct) >= 0 ? 'bt-profit' : 'bt-loss'}`}>
                                          {t.is_open ? '-' : formatPct(parseFloat(t.pnl_pct))}
                                        </td>
                                        <td>{t.duration_candles ?? '-'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                                {expandedRunData.trades.length > 20 && (
                                  <div className="bt-run-trades-more">
                                    ...und {expandedRunData.trades.length - 20} weitere Trades
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </>
                      ) : null}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Disclaimer */}
      <div className="bt-disclaimer">
        Alpha Backtest basiert auf historischen Preisdaten und stellt keine Anlageberatung dar.
        Vergangene Ergebnisse garantieren keine zukuenftigen Resultate.
        Orderbook- und Funding-Daten sind historisch nicht verfuegbar — der Backtest nutzt nur Z-Score und Lead-Lag Faktoren.
      </div>
    </div>
  );
};

export default Backtest;
