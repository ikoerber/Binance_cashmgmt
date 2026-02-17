/**
 * CombinedScore - Combined Score Dashboard
 *
 * Vereint MacroSignal (Richtung, 60%) und Sentiment (Sizing, 40%)
 * zu einer einheitlichen Handlungsempfehlung mit Unified Score (-100 bis +100).
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCombinedScore, getSettings } from '../api/client';
import { formatNumber } from '../utils/formatters';
import './CombinedScore.css';

const QUALITY_LABELS = {
  full: 'Vollstaendig',
  partial: 'Eingeschraenkt',
  degraded: 'Unzuverlaessig',
};

const MACRO_REC_COLORS = {
  'STARK LONG': '#16a34a',
  'LONG': '#22c55e',
  'NEUTRAL': '#64748b',
  'SHORT': '#f97316',
  'STARK SHORT': '#dc2626',
};

const CombinedScore = ({ userId = 'user_123' }) => {
  const [showMacroDetail, setShowMacroDetail] = useState(false);
  const [showSentimentDetail, setShowSentimentDetail] = useState(false);

  const { data: settings } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
  });

  const interval = settings?.macro_signal_interval || '15';

  const { data, isLoading, error } = useQuery({
    queryKey: ['combined-score', userId, interval],
    queryFn: () => getCombinedScore(userId, interval),
    refetchInterval: interval === '1' ? 30000 : interval === '5' ? 45000 : 60000,
  });

  if (isLoading) return <div className="combined-loading">Lade Combined Score...</div>;
  if (error) return <div className="combined-error">Fehler: {error.message}</div>;
  if (!data) return null;

  const scorePosition = ((data.unified_score + 100) / 200) * 100;

  return (
    <div className="combined-container">
      {/* Header */}
      <div className="combined-header">
        <div className="combined-header-left">
          <h2>Combined Score <span>BTC/EUR</span></h2>
          <span className="combined-interval-badge">{interval}-Min</span>
          <span className={`combined-quality-badge quality-${data.overall_quality}`}>
            {QUALITY_LABELS[data.overall_quality] || data.overall_quality}
          </span>
        </div>
        <div className="combined-header-right">
          <span className="combined-confidence">
            Confidence: {formatNumber(data.confidence * 100, 0)}%
          </span>
          <span className="combined-timestamp">
            {new Date(data.timestamp).toLocaleTimeString('de-DE')}
          </span>
        </div>
      </div>

      {/* Hero Action Banner */}
      <div className="combined-action-banner" style={{ '--action-color': data.action_color }}>
        <div className="combined-action-main">
          <span className="combined-action-label" style={{ color: data.action_color }}>
            {data.action}
          </span>
          <span className="combined-multiplier" style={{ color: data.size_multiplier > 1 ? '#16a34a' : data.size_multiplier < 1 ? '#dc2626' : '#64748b' }}>
            {formatNumber(data.size_multiplier, 2)}x
          </span>
        </div>

        {/* Unified Score Bar */}
        <div className="combined-score-bar-section">
          <div className="combined-score-labels">
            <span>-100</span>
            <span>Sell</span>
            <span>0</span>
            <span>Buy</span>
            <span>+100</span>
          </div>
          <div className="combined-score-track">
            <div className="combined-score-center-mark" />
            {/* Threshold marks */}
            <div className="combined-score-threshold" style={{ left: '20%' }} title="-60" />
            <div className="combined-score-threshold" style={{ left: '35%' }} title="-30" />
            <div className="combined-score-threshold" style={{ left: '45%' }} title="-10" />
            <div className="combined-score-threshold" style={{ left: '55%' }} title="+10" />
            <div className="combined-score-threshold" style={{ left: '65%' }} title="+30" />
            <div className="combined-score-threshold" style={{ left: '80%' }} title="+60" />
            {/* Score indicator */}
            <div
              className="combined-score-indicator"
              style={{
                left: `${Math.max(2, Math.min(98, scorePosition))}%`,
                backgroundColor: data.action_color,
              }}
            />
          </div>
          <div className="combined-score-value">
            Score: <strong>{data.unified_score > 0 ? '+' : ''}{formatNumber(data.unified_score, 1)}</strong>
            {' '}| Intensity: <strong>{formatNumber(data.intensity * 100, 0)}%</strong>
          </div>
        </div>
      </div>

      {/* Conflict Alert */}
      {!data.signals_aligned && data.conflict_description && (
        <div className="combined-conflict-alert">
          <span className="combined-conflict-icon">&#9888;</span>
          <span>{data.conflict_description}</span>
        </div>
      )}

      {/* Sub-Signal Cards */}
      <div className="combined-subsignals">
        {/* MacroSignal Card */}
        <div className="combined-subsignal-card">
          <div className="combined-subsignal-header">
            <h3>Makro-Signal</h3>
            <span className="combined-weight-badge">60%</span>
          </div>
          <div className="combined-subsignal-body">
            <span
              className="combined-rec-badge"
              style={{ backgroundColor: MACRO_REC_COLORS[data.direction.recommendation] || '#64748b' }}
            >
              {data.direction.recommendation}
            </span>
            <div className="combined-subsignal-metrics">
              <div className="combined-metric">
                <span className="combined-metric-label">Raw Score</span>
                <span className="combined-metric-value">
                  {data.direction.composite_raw > 0 ? '+' : ''}{data.direction.composite_raw} / 8
                </span>
              </div>
              <div className="combined-metric">
                <span className="combined-metric-label">Faktoren</span>
                <span className="combined-metric-value">
                  {data.direction.active_factors}/{data.direction.total_factors}
                </span>
              </div>
              <div className="combined-metric">
                <span className="combined-metric-label">Intervall</span>
                <span className="combined-metric-value">{data.direction.interval_minutes}m</span>
              </div>
            </div>
          </div>
          {data.macro_detail?.scores?.length > 0 && (
            <button
              className="combined-detail-toggle"
              onClick={() => setShowMacroDetail(!showMacroDetail)}
            >
              {showMacroDetail ? 'Details ausblenden' : 'Details anzeigen'}
            </button>
          )}
          {showMacroDetail && data.macro_detail?.scores && (
            <div className="combined-detail-section">
              {data.macro_detail.scores.map((s, i) => (
                <div key={i} className="combined-factor-row">
                  <span className="combined-factor-name">
                    {s.factor}
                    <span className={`combined-factor-dir ${s.direction}`}>
                      {s.direction === 'direct' ? '(↑=↑)' : '(↑=↓)'}
                    </span>
                  </span>
                  <div className="combined-factor-bar-track">
                    <div
                      className={`combined-factor-bar-fill ${s.score > 0 ? 'positive' : s.score < 0 ? 'negative' : 'neutral'}`}
                      style={{
                        left: s.score >= 0 ? '50%' : `${50 + (s.score / 2) * 50}%`,
                        width: `${Math.abs(s.score) / 2 * 50}%`,
                      }}
                    />
                    <div className="combined-factor-bar-center" />
                  </div>
                  <span className={`combined-factor-score ${s.score > 0 ? 'positive' : s.score < 0 ? 'negative' : ''}`}>
                    {s.score > 0 ? '+' : ''}{s.score}
                  </span>
                  <span className="combined-factor-reason">{s.reason}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Sentiment Card */}
        <div className="combined-subsignal-card">
          <div className="combined-subsignal-header">
            <h3>Sentiment</h3>
            <span className="combined-weight-badge">40%</span>
          </div>
          <div className="combined-subsignal-body">
            <span
              className="combined-rec-badge"
              style={{ backgroundColor: data.action_color }}
            >
              {data.sizing.label}
            </span>
            <div className="combined-subsignal-metrics">
              <div className="combined-metric">
                <span className="combined-metric-label">Score</span>
                <span className="combined-metric-value">
                  {formatNumber(data.sizing.composite_score, 1)}
                </span>
              </div>
              <div className="combined-metric">
                <span className="combined-metric-label">Multiplikator</span>
                <span className="combined-metric-value" style={{ color: data.sizing.buy_size_multiplier > 1 ? '#16a34a' : data.sizing.buy_size_multiplier < 1 ? '#dc2626' : '#64748b' }}>
                  {formatNumber(data.sizing.buy_size_multiplier, 2)}x
                </span>
              </div>
              <div className="combined-metric">
                <span className="combined-metric-label">Pillars</span>
                <span className="combined-metric-value">
                  {data.sizing.active_pillars}/{data.sizing.total_pillars}
                </span>
              </div>
            </div>
          </div>
          {data.sentiment_detail?.pillars?.length > 0 && (
            <button
              className="combined-detail-toggle"
              onClick={() => setShowSentimentDetail(!showSentimentDetail)}
            >
              {showSentimentDetail ? 'Details ausblenden' : 'Details anzeigen'}
            </button>
          )}
          {showSentimentDetail && data.sentiment_detail?.pillars && (
            <div className="combined-detail-section">
              {data.sentiment_detail.pillars.map((p, i) => (
                <div key={i} className="combined-pillar-row">
                  <span className="combined-pillar-name">{p.name}</span>
                  <div className="combined-pillar-bar-track">
                    <div
                      className="combined-pillar-bar-fill"
                      style={{
                        width: `${p.score}%`,
                        background: p.score <= 25
                          ? 'linear-gradient(90deg, #dc2626, #f97316)'
                          : p.score <= 40
                            ? 'linear-gradient(90deg, #f97316, #fb923c)'
                            : p.score <= 60
                              ? 'linear-gradient(90deg, #94a3b8, #64748b)'
                              : p.score <= 75
                                ? 'linear-gradient(90deg, #4ade80, #22c55e)'
                                : 'linear-gradient(90deg, #22c55e, #16a34a)',
                      }}
                    />
                  </div>
                  <span className="combined-pillar-score">{formatNumber(p.score, 0)}</span>
                  <span className={`combined-pillar-quality quality-${p.quality}`}>
                    {p.quality === 'live' ? 'Live' : p.quality === 'cached' ? 'Cached' : p.quality === 'stale' ? 'Veraltet' : 'N/A'}
                  </span>
                </div>
              ))}
              {data.sentiment_detail.dispersion && (
                <div className="combined-dispersion-info">
                  Pillar-Uebereinstimmung: {formatNumber(data.sentiment_detail.dispersion.confidence_factor * 100, 0)}%
                  {data.sentiment_detail.dispersion.high_dispersion && (
                    <span className="combined-dispersion-warn"> (hohe Streuung)</span>
                  )}
                </div>
              )}
              {data.sentiment_detail.volatility && (
                <div className="combined-vol-info">
                  Volatilitaets-Regime: <strong>{data.sentiment_detail.volatility.regime}</strong>
                  {' '}(Ratio: {formatNumber(data.sentiment_detail.volatility.vol_ratio, 2)}, Scaling: {formatNumber(data.sentiment_detail.volatility.scaling_factor, 1)}x)
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Quality Reason */}
      {data.quality_reason && (
        <div className="combined-quality-note">
          Einschraenkung: {data.quality_reason}
        </div>
      )}

      {/* Disclaimer */}
      <div className="combined-disclaimer">
        Indikativ, keine Handelsempfehlung. Combined Score kombiniert kurzfristige Makro-Richtung
        mit mittelfristigem Sentiment-Sizing und ersetzt keine eigene Analyse.
        Gewichtung: Makro-Signal 60%, Sentiment 40%.
      </div>
    </div>
  );
};

export default CombinedScore;
