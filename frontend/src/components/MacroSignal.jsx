/**
 * MacroSignal - Makro-Signal Dashboard
 *
 * Zeigt 4 Makro-Faktoren und eine konfigurierbare Richtungsempfehlung fuer BTC/EUR.
 * Intervall (1m/5m/15m) wird aus User-Settings geladen.
 * Richtungseinfluss (bullish/bearish) wird visuell auf Indikator-Karten dargestellt.
 */
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMacroSignals, getSettings } from '../api/client';
import { formatNumber } from '../utils/formatters';
import './MacroSignal.css';

const MacroSignal = ({ userId = 'user_123' }) => {
  const [countdown, setCountdown] = useState('');

  // Settings laden fuer Signal-Intervall
  const { data: settings } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
  });

  const interval = settings?.macro_signal_interval || '15';

  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ['macro-signals', interval],
    queryFn: () => getMacroSignals(interval),
    refetchInterval: interval === '1' ? 30000 : interval === '5' ? 45000 : 60000,
  });

  const intervalMinutes = data?.interval_minutes || parseInt(interval);

  // Countdown bis zum naechsten Update
  useEffect(() => {
    if (!data?.next_update) return;
    const timer = setInterval(() => {
      const now = new Date();
      const next = new Date(data.next_update + 'Z');
      const diff = next - now;
      if (diff <= 0) {
        setCountdown('Aktualisiert...');
        return;
      }
      const mins = Math.floor(diff / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      setCountdown(`${mins}:${secs.toString().padStart(2, '0')}`);
    }, 1000);
    return () => clearInterval(timer);
  }, [data?.next_update]);

  const formatPct = (num) => {
    if (num === null || num === undefined) return '';
    const val = parseFloat(num);
    return `${val >= 0 ? '+' : ''}${formatNumber(val, 3)}%`;
  };

  const getChangeClass = (num) => {
    if (num === null || num === undefined) return '';
    return parseFloat(num) >= 0 ? 'change-positive' : 'change-negative';
  };

  const getScoreClass = (score) => {
    if (score > 0) return 'score-positive';
    if (score < 0) return 'score-negative';
    return 'score-neutral';
  };

  const getQualityLabel = (quality) => {
    const labels = {
      live: 'Live',
      cached: 'Cached',
      stale: 'Veraltet',
      unavailable: 'N/A',
    };
    return labels[quality] || quality;
  };

  /**
   * Berechnet den Richtungseinfluss-Badge fuer eine Indikator-Karte.
   * Zeigt an, ob die aktuelle Bewegung bullish oder bearish fuer BTC/EUR ist.
   */
  const getInfluenceBadge = (influence, changePct) => {
    if (!influence || influence === 'info') return null;

    const val = changePct !== null && changePct !== undefined ? parseFloat(changePct) : 0;
    const isPositive = val > 0.001;
    const isNegative = val < -0.001;

    let effectClass = 'influence-neutral';
    let arrow = '\u2192';  // →
    let label = 'BTC/EUR';

    if (influence === 'direct') {
      if (isPositive) { effectClass = 'influence-bullish'; arrow = '\u2191'; label = '\u2191 BTC/EUR'; }
      else if (isNegative) { effectClass = 'influence-bearish'; arrow = '\u2193'; label = '\u2193 BTC/EUR'; }
      else { label = '\u2192 BTC/EUR'; }
    } else if (influence === 'inverse') {
      // Invers: positive Aenderung = bearish fuer BTC/EUR
      if (isPositive) { effectClass = 'influence-bearish'; arrow = '\u2193'; label = '\u2193 BTC/EUR'; }
      else if (isNegative) { effectClass = 'influence-bullish'; arrow = '\u2191'; label = '\u2191 BTC/EUR'; }
      else { label = '\u2192 BTC/EUR'; }
    }

    return (
      <span className={`influence-badge ${effectClass}`} title={
        influence === 'direct'
          ? 'Direkter Einfluss: steigt zusammen mit BTC/EUR'
          : 'Inverser Einfluss: steigt = BTC/EUR faellt'
      }>
        {label}
      </span>
    );
  };

  // Indikator-Konfiguration fuer die Anzeige
  const indicatorConfig = [
    {
      key: 'btc_eur', label: 'BTC/EUR', decimals: 2, unit: ' \u20ac', primary: true,
      desc: 'Aktueller Bitcoin-Kurs in Euro. Dein Haupt-Handelspaar.',
      influence: null,  // Ist das Zielpaar, kein Richtungs-Badge
    },
    {
      key: 'btc_usd', label: 'BTC/USD', decimals: 2, unit: ' $',
      desc: 'Bitcoin in US-Dollar. Haupttreiber: Krypto-Momentum und globale Liquiditaet.',
      influence: 'direct',  // BTC/USD hoch = BTC/EUR hoch
    },
    {
      key: 'eur_usd', label: 'EUR/USD', decimals: 4, unit: '',
      desc: 'Wechselkurs Euro/Dollar. Steigt EUR, faellt BTC/EUR bei gleichem BTC/USD.',
      influence: 'inverse',  // EUR staerker = BTC/EUR runter
    },
    {
      key: 'dxy', label: 'DXY (UUP)', decimals: 2, unit: '',
      desc: 'US Dollar Index (via UUP ETF). Starker Dollar = Gegenwind fuer BTC.',
      influence: 'inverse',  // USD staerker = BTC runter
    },
    {
      key: 'us02y', label: 'US 2Y Yield', decimals: 3, unit: '%',
      desc: 'US 2-Jahres-Staatsanleihe. Quelle: FRED (Tageswert).',
      influence: 'info',  // Einzelkomponente des Spreads
    },
    {
      key: 'de02y', label: 'DE 2Y Yield', decimals: 3, unit: '%',
      desc: 'Deutsche 2-Jahres-Bundesanleihe. Quelle: EZB (Tageswert).',
      influence: 'info',  // Einzelkomponente des Spreads
    },
    {
      key: 'spread', label: 'Spread US-DE', decimals: 3, unit: '%',
      desc: 'US02Y minus DE02Y. Weitung = USD attraktiver = Druck auf BTC.',
      influence: 'inverse',  // Spread steigt = bearish BTC
    },
  ];

  if (isLoading) return <div className="loading">Lade Makro-Signale...</div>;
  if (error) return <div className="error">Fehler: {error.message}</div>;
  if (!data) return null;

  const indicators = data.indicators || {};
  const scores = data.scores || [];

  return (
    <div className="macro-signal-container">
      {/* Header */}
      <div className="macro-header">
        <h2>Makro-Signal <span>BTC/EUR</span></h2>
        <div className="macro-meta">
          <span className="interval-badge">{intervalMinutes}-Min</span>
          {countdown && (
            <span className="countdown-badge">
              Naechstes Update: {countdown}
            </span>
          )}
          {dataUpdatedAt && (
            <span className="last-update">
              Abgerufen: {new Date(dataUpdatedAt).toLocaleTimeString('de-DE')}
            </span>
          )}
        </div>
      </div>

      {/* Empfehlungs-Banner */}
      <div
        className={`recommendation-banner recommendation-${data.composite_score}`}
        style={{ '--rec-color': data.recommendation_color }}
      >
        <div className="rec-label">{intervalMinutes}-Min Signal</div>
        <div className="rec-value">{data.recommendation}</div>
        <div className="rec-score">
          Score: {data.composite_raw} / {data.active_factors * 2}
          {data.active_factors < data.total_factors && (
            <span className="rec-warning">
              ({data.active_factors}/{data.total_factors} Faktoren aktiv)
            </span>
          )}
        </div>
      </div>

      {/* Indikator-Karten */}
      <div className="indicator-grid">
        {indicatorConfig.map(({ key, label, decimals, unit, primary, desc, influence }) => {
          const ind = indicators[key];
          if (!ind) return null;
          return (
            <div key={key} className={`indicator-card ${primary ? 'indicator-primary' : ''} ${ind.quality === 'unavailable' ? 'indicator-unavailable' : ''}`}>
              <div className="indicator-header">
                <span className="indicator-label">{label}</span>
                <div className="indicator-badges">
                  {getInfluenceBadge(influence, ind.change_pct)}
                  <span className={`quality-badge quality-${ind.quality}`}>
                    {getQualityLabel(ind.quality)}
                  </span>
                </div>
              </div>
              <div className="indicator-value">
                {ind.current !== null ? `${formatNumber(ind.current, decimals)}${unit}` : 'N/A'}
              </div>
              {ind.change_pct !== null && ind.change_pct !== undefined && (
                <div className={`indicator-change ${getChangeClass(ind.change_pct)}`}>
                  {formatPct(ind.change_pct)}
                  <span className="change-period">{intervalMinutes} Min</span>
                </div>
              )}
              {ind.previous_15m !== null && ind.previous_15m !== undefined && (
                <div className="indicator-prev">
                  Vor {intervalMinutes}m: {formatNumber(ind.previous_15m, decimals)}{unit}
                </div>
              )}
              <div className="indicator-desc">{desc}</div>
            </div>
          );
        })}
      </div>

      {/* Score-Breakdown */}
      <div className="score-breakdown">
        <h3>Signal-Analyse</h3>
        <div className="score-list">
          {scores.map((score, idx) => (
            <div key={idx} className="score-row">
              <div className="score-factor-col">
                <div className="score-factor">
                  {score.factor}
                  {score.direction && (
                    <span className={`score-direction score-dir-${score.direction}`}>
                      {score.direction === 'direct' ? '\u2191=\u2191' : '\u2191=\u2193'}
                    </span>
                  )}
                </div>
                <div className="score-factor-desc">
                  {score.direction === 'direct'
                    ? 'Direkt: steigt = bullish BTC/EUR'
                    : 'Invers: steigt = bearish BTC/EUR'}
                </div>
              </div>
              <div className="score-bar-container">
                <div className="score-bar-track">
                  <div className="score-bar-center" />
                  <div
                    className={`score-bar-fill ${getScoreClass(score.score)}`}
                    style={{
                      left: score.score >= 0 ? '50%' : `${50 + score.score * 12.5}%`,
                      width: `${Math.abs(score.score) * 12.5}%`,
                    }}
                  />
                  {[-2, -1, 0, 1, 2].map((tick) => (
                    <div
                      key={tick}
                      className={`score-tick ${score.score === tick ? 'active' : ''}`}
                      style={{ left: `${(tick + 2) * 25}%` }}
                    />
                  ))}
                </div>
                <span className={`score-value ${getScoreClass(score.score)}`}>
                  {score.score > 0 ? '+' : ''}{score.score}
                </span>
              </div>
              <div className="score-reason">{score.reason}</div>
            </div>
          ))}
        </div>

        {/* Komposit */}
        <div className="composite-row">
          <div className="composite-label">Gesamt</div>
          <div className="composite-value" style={{ color: data.recommendation_color }}>
            {data.composite_raw > 0 ? '+' : ''}{data.composite_raw}
          </div>
          <div className="composite-rec" style={{ color: data.recommendation_color }}>
            {data.recommendation}
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="macro-disclaimer">
        Indikativ, keine Handelsempfehlung. Signal basiert auf kurzfristigen Makro-Indikatoren und ersetzt keine eigene Analyse.
      </div>
    </div>
  );
};

export default MacroSignal;
