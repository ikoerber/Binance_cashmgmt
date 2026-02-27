/**
 * DecisionLog - Filterable decision log with expandable rows
 *
 * Route: /s/:symbol/bot/decisions
 * Shows all dry-run decisions with filtering by date, action, symbol.
 * Expandable rows reveal factor detail bars, regime info, trade details.
 */
import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import { getDryRunDecisions } from '../api/client';
import { formatNumber, formatEUR, formatDate, formatTime } from '../utils/formatters';
import './DecisionLog.css';

/**
 * Map factor score from [-5, +5] to percentage [0, 100] for bar display.
 */
const scoreToBarPct = (score) => {
  const clamped = Math.max(-5, Math.min(5, score || 0));
  return ((clamped + 5) / 10) * 100;
};

const ACTION_OPTIONS = [
  { value: '', label: 'Alle' },
  { value: 'BUY', label: 'BUY' },
  { value: 'SELL', label: 'SELL' },
  { value: 'HOLD', label: 'HOLD' },
  { value: 'NO_SIGNAL', label: 'NO_SIGNAL' },
];

const actionColor = (action) => {
  switch (action) {
    case 'BUY': return '#16a34a';
    case 'SELL': return '#dc2626';
    case 'HOLD': return '#64748b';
    case 'NO_SIGNAL': return '#94a3b8';
    default: return '#64748b';
  }
};

const signalColor = (signal) => {
  if (signal === 'LONG') return '#16a34a';
  if (signal === 'SHORT') return '#dc2626';
  return '#64748b';
};

const qualityLabel = (q) => {
  if (q === 'full') return 'Vollstaendig';
  if (q === 'partial') return 'Teilweise';
  return 'Eingeschraenkt';
};

const DecisionLog = () => {
  const { symbol } = useSymbol();
  const { userId } = useUser();

  const [filters, setFilters] = useState({
    fromDate: '',
    toDate: '',
    action: '',
    symbol: symbol,
  });
  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ['dry-run-decisions', userId, filters, offset],
    queryFn: () => getDryRunDecisions(userId, {
      fromDate: filters.fromDate || undefined,
      toDate: filters.toDate || undefined,
      action: filters.action || undefined,
      symbol: filters.symbol || undefined,
      limit: 50,
      offset: offset,
    }),
    refetchInterval: 30000,
  });

  const decisions = data?.decisions ?? [];
  const total = data?.total ?? 0;

  const handleFilterChange = useCallback((key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setOffset(0);
  }, []);

  const handleResetFilters = () => {
    setFilters({ fromDate: '', toDate: '', action: '', symbol: symbol });
    setOffset(0);
  };

  const handleLoadMore = () => {
    setOffset(prev => prev + 50);
  };

  const toggleExpanded = (id) => {
    setExpandedId(prev => prev === id ? null : id);
  };

  // Factor display labels
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

  return (
    <div className="decision-log-container">
      <div className="decision-header">
        <h2>Decision Log</h2>
        <span className="decision-total">{total} Entscheidungen</span>
      </div>

      {/* Filter Bar */}
      <div className="decision-filters">
        <div className="decision-filter-field">
          <label>Von</label>
          <input
            type="date"
            value={filters.fromDate}
            onChange={(e) => handleFilterChange('fromDate', e.target.value)}
          />
        </div>
        <div className="decision-filter-field">
          <label>Bis</label>
          <input
            type="date"
            value={filters.toDate}
            onChange={(e) => handleFilterChange('toDate', e.target.value)}
          />
        </div>
        <div className="decision-filter-field">
          <label>Action</label>
          <select
            value={filters.action}
            onChange={(e) => handleFilterChange('action', e.target.value)}
          >
            {ACTION_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div className="decision-filter-field">
          <label>Symbol</label>
          <select
            value={filters.symbol}
            onChange={(e) => handleFilterChange('symbol', e.target.value)}
          >
            <option value="">Alle</option>
            <option value="BTCEUR">BTCEUR</option>
            <option value="XRPEUR">XRPEUR</option>
            <option value="ETHEUR">ETHEUR</option>
          </select>
        </div>
        <button className="decision-filter-reset" onClick={handleResetFilters}>
          Reset
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="decision-loading">Lade Entscheidungen...</div>
      ) : decisions.length === 0 ? (
        <div className="decision-empty">
          Noch keine Entscheidungen protokolliert. Aktiviere den Dry-Run Modus im Bot Dashboard.
        </div>
      ) : (
        <>
          <div className="decision-table-wrapper">
            <table className="decision-table">
              <thead>
                <tr>
                  <th>Zeit</th>
                  <th>Action</th>
                  <th>Alpha Score</th>
                  <th>Preis</th>
                  <th>Signal</th>
                  <th>Qualitaet</th>
                  <th>Grund</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map(d => (
                  <DecisionRow
                    key={d.id}
                    decision={d}
                    isExpanded={expandedId === d.id}
                    onToggle={() => toggleExpanded(d.id)}
                    factorLabels={factorLabels}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {(offset + 50) < total && (
            <div className="decision-load-more-container">
              <button className="decision-load-more" onClick={handleLoadMore}>
                Mehr laden ({Math.min(offset + 50, total)} von {total})
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

/**
 * Single decision row with expandable detail.
 */
const DecisionRow = ({ decision, isExpanded, onToggle, factorLabels }) => {
  const d = decision;
  const factors = d.factors ?? [];
  const signal = d.trade_signal ?? d.signal ?? 'NEUTRAL';
  const quality = d.quality ?? 'degraded';
  const reason = d.reason ?? '';
  const truncatedReason = reason.length > 60 ? reason.slice(0, 60) + '...' : reason;
  const alphaScore = d.alpha_score ?? 0;
  const isPositiveScore = alphaScore > 0;

  return (
    <>
      <tr
        className={`decision-row ${isExpanded ? 'expanded' : ''}`}
        onClick={onToggle}
        title="Klicken fuer Details"
      >
        <td className="decision-cell-time">
          <span className="decision-date">{formatDate(d.evaluated_at)}</span>
          <span className="decision-time">{formatTime(d.evaluated_at)}</span>
        </td>
        <td>
          <span
            className="decision-action-badge"
            style={{ background: actionColor(d.action) }}
          >
            {d.action}
          </span>
        </td>
        <td>
          <span className={`decision-score ${isPositiveScore ? 'positive' : alphaScore < 0 ? 'negative' : ''}`}>
            {parseFloat(alphaScore).toFixed(2)}
          </span>
        </td>
        <td>{d.price != null ? formatEUR(d.price) : '--'}</td>
        <td>
          <span
            className="decision-signal-badge"
            style={{ color: signalColor(signal) }}
          >
            {signal}
          </span>
        </td>
        <td>
          <span className={`decision-quality-badge quality-${quality}`}>
            {qualityLabel(quality)}
          </span>
        </td>
        <td className="decision-cell-reason" title={reason}>
          {truncatedReason}
        </td>
      </tr>

      {/* Expanded Detail */}
      {isExpanded && (
        <tr className="decision-row-expanded">
          <td colSpan={7}>
            <div className="decision-detail">
              {/* Factor Bars */}
              {factors.length > 0 && (
                <div className="decision-factor-section">
                  <h4>Faktor-Scores</h4>
                  <div className="decision-factor-bars">
                    {factors.map((f, i) => {
                      const name = factorLabels[f.name] || factorLabels[f.factor] || f.name || f.factor || 'Unknown';
                      const score = f.score ?? f.value ?? 0;
                      const pct = scoreToBarPct(score);
                      const isPositive = score > 0;
                      const isNeutral = Math.abs(score) < 0.01;
                      return (
                        <div key={i} className="bot-factor-bar">
                          <span className="bot-factor-label">{name}</span>
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
                          <span className={`bot-factor-score ${isPositive ? 'positive' : score < 0 ? 'negative' : ''}`}>
                            {parseFloat(score).toFixed(2)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Detail Grid */}
              <div className="decision-detail-grid">
                {d.trailing_stop_level != null && (
                  <div className="decision-detail-item">
                    <span className="decision-detail-label">Trailing Stop</span>
                    <span className="decision-detail-value">{formatEUR(d.trailing_stop_level)}</span>
                  </div>
                )}
                {d.regime && (
                  <div className="decision-detail-item">
                    <span className="decision-detail-label">Regime</span>
                    <span className="decision-detail-value">
                      {typeof d.regime === 'string' ? d.regime : d.regime.label ?? d.regime.regime ?? '--'}
                      {d.hurst_exponent != null && ` (H: ${parseFloat(d.hurst_exponent).toFixed(2)})`}
                    </span>
                  </div>
                )}
                {d.symbol && (
                  <div className="decision-detail-item">
                    <span className="decision-detail-label">Symbol</span>
                    <span className="decision-detail-value">{d.symbol}</span>
                  </div>
                )}
              </div>

              {/* Virtual Trade Details */}
              {(d.action === 'BUY' || d.action === 'SELL') && d.trade_qty != null && (
                <div className="decision-trade-section">
                  <h4>Virtueller Trade</h4>
                  <div className="decision-detail-grid">
                    <div className="decision-detail-item">
                      <span className="decision-detail-label">Menge</span>
                      <span className="decision-detail-value">{formatNumber(d.trade_qty, 8)}</span>
                    </div>
                    {d.trade_price != null && (
                      <div className="decision-detail-item">
                        <span className="decision-detail-label">Preis (nach Slippage)</span>
                        <span className="decision-detail-value">{formatEUR(d.trade_price)}</span>
                      </div>
                    )}
                    {d.trade_fee != null && (
                      <div className="decision-detail-item">
                        <span className="decision-detail-label">Fee</span>
                        <span className="decision-detail-value">{formatEUR(d.trade_fee)}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Full Reason */}
              {reason && (
                <div className="decision-reason-full">
                  <h4>Begr&uuml;ndung</h4>
                  <p>{reason}</p>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

export default DecisionLog;
