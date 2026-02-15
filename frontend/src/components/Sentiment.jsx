import { useQuery } from '@tanstack/react-query';
import { getSentiment } from '../api/client';
import { formatNumber } from '../utils/formatters';
import './Sentiment.css';

const getQualityLabel = (quality) => {
  const labels = {
    live: 'Live',
    cached: 'Cached',
    stale: 'Veraltet',
    unavailable: 'N/A',
  };
  return labels[quality] || quality;
};

const getScoreGradient = (score) => {
  if (score <= 25) return 'linear-gradient(90deg, #dc2626, #f97316)';
  if (score <= 40) return 'linear-gradient(90deg, #f97316, #fb923c)';
  if (score <= 60) return 'linear-gradient(90deg, #94a3b8, #64748b)';
  if (score <= 75) return 'linear-gradient(90deg, #4ade80, #22c55e)';
  return 'linear-gradient(90deg, #22c55e, #16a34a)';
};

const PILLAR_EXPLANATIONS = {
  'Fear & Greed': 'Aggregierter Stimmungsindex aus Social Media, Volatilitaet und Marktdynamik. Niedrig = Angst im Markt, Hoch = Gier/Euphorie.',
  'Funding Rate': 'Kosten fuer gehebelte Positionen auf Derivate-Boersen. Positiv = Longs zahlen Shorts (bullish), Negativ = Shorts zahlen Longs (bearish).',
  'Taker Buy/Sell Ratio': 'Verhaeltnis aggressiver Kaeufer zu Verkaeufern (7-Tage-Schnitt). Ueber 1.0 = mehr Kaufdruck, unter 1.0 = mehr Verkaufsdruck.',
  'Trend-Deviation (DMA)': 'Abstand des BTC-Preises zum 50-Tage-Durchschnitt, gewichtet nach Marktregime (bullish/bearish via 50 vs 200 DMA).',
  'Volume-Momentum': 'Heutiges Handelsvolumen relativ zum 20-Tage-Schnitt. Hohes Volumen bei steigendem Preis = Greed, bei fallendem = Fear.',
};

const formatRawValue = (name, value) => {
  if (name === 'Fear & Greed') return `${Math.round(value)}`;
  if (name === 'Funding Rate') return `${formatNumber(value * 100, 4)}%`;
  if (name === 'Taker Buy/Sell Ratio') return formatNumber(value, 3);
  if (name === 'Trend-Deviation (DMA)') return `${formatNumber(value, 1)}%`;
  if (name === 'Volume-Momentum') return `${formatNumber(value, 2)}x`;
  return formatNumber(value, 2);
};

const Sentiment = ({ userId = 'user_123' }) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['sentiment', userId],
    queryFn: () => getSentiment(userId),
    refetchInterval: 60000,
  });

  if (isLoading) return <div className="sentiment-loading">Lade Sentiment-Daten...</div>;
  if (error) return <div className="sentiment-error">Fehler: {error.message}</div>;
  if (!data) return null;

  const gaugeRotation = (data.composite_score / 100) * 180;
  const rec = data.recommendation;
  const disp = data.dispersion;
  const vol = data.volatility;

  return (
    <div className="sentiment-container">
      {/* Header */}
      <div className="sentiment-header">
        <h2>Sentiment Score <span>BTC/EUR</span></h2>
        <div className="sentiment-meta">
          {data.active_pillars < data.total_pillars && (
            <span className="sentiment-pillars-badge">
              {data.active_pillars}/{data.total_pillars} Pillars aktiv
            </span>
          )}
          <span className="sentiment-timestamp">
            {data.timestamp
              ? new Date(data.timestamp).toLocaleTimeString('de-DE')
              : ''}
          </span>
        </div>
      </div>

      {/* Gauge */}
      <div className="sentiment-gauge-section">
        <div className="sentiment-gauge-container">
          <div
            className="sentiment-gauge"
            style={{ '--gauge-rotation': `${gaugeRotation}deg` }}
          >
            <div className="sentiment-gauge-needle" />
            <div className="sentiment-gauge-center">
              <div className="sentiment-gauge-score">
                {formatNumber(data.composite_score, 1)}
              </div>
              <div
                className="sentiment-gauge-label"
                style={{ color: data.composite_color }}
              >
                {data.composite_label}
              </div>
            </div>
          </div>
          <div className="sentiment-gauge-scale">
            <span className="scale-label scale-fear">Fear</span>
            <span className="scale-label scale-neutral">Neutral</span>
            <span className="scale-label scale-greed">Greed</span>
          </div>
        </div>
      </div>

      {/* Recommendation */}
      <div className="sentiment-recommendation">
        <div className="sentiment-rec-header">
          <h3>Empfehlung</h3>
        </div>
        <div className="sentiment-rec-content">
          <div
            className="sentiment-rec-action"
            style={{ color: data.composite_color }}
          >
            {rec.action}
          </div>
          <div className="sentiment-rec-multiplier">
            <span className="rec-multiplier-label">Kaufgroessen-Multiplikator</span>
            <span
              className={`rec-multiplier-value ${
                rec.buy_size_multiplier > 1
                  ? 'multiplier-up'
                  : rec.buy_size_multiplier < 1
                    ? 'multiplier-down'
                    : ''
              }`}
            >
              {formatNumber(rec.buy_size_multiplier, 2)}x
            </span>
            <div className="rec-multiplier-detail">
              Roh: {formatNumber(rec.raw_multiplier, 3)}x
              {Math.abs(rec.buy_size_multiplier - rec.raw_multiplier) > 0.001 && (
                <span className="rec-adjusted-hint">
                  (angepasst durch Dispersion + Volatilitaet)
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Pillar Cards */}
      <div className="sentiment-pillars">
        <h3>Pillar-Analyse</h3>
        <div className="sentiment-pillar-grid">
          {data.pillars.map((pillar, idx) => (
            <div
              key={idx}
              className={`sentiment-pillar-card ${
                pillar.quality === 'unavailable' ? 'pillar-unavailable' : ''
              }`}
            >
              <div className="pillar-header">
                <span className="pillar-name">{pillar.name}</span>
                <span
                  className={`pillar-quality-badge quality-${pillar.quality}`}
                >
                  {getQualityLabel(pillar.quality)}
                </span>
              </div>
              <div className="pillar-score-value">
                {formatNumber(pillar.score, 1)}
              </div>
              <div className="pillar-bar-track">
                <div
                  className="pillar-bar-fill"
                  style={{
                    width: `${pillar.score}%`,
                    background: getScoreGradient(pillar.score),
                  }}
                />
              </div>
              {pillar.raw_value !== null && (
                <div className="pillar-raw">
                  Roh: {formatRawValue(pillar.name, pillar.raw_value)}
                </div>
              )}
              <div className="pillar-source">Quelle: {pillar.source}</div>
              {PILLAR_EXPLANATIONS[pillar.name] && (
                <div className="pillar-explanation">
                  {PILLAR_EXPLANATIONS[pillar.name]}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Analysis: Dispersion + Volatility */}
      <div className="sentiment-analysis-grid">
        {/* Dispersion / Confidence */}
        <div className="sentiment-analysis-card">
          <h3>Pillar-Uebereinstimmung</h3>
          <div className="analysis-main-value">
            {formatNumber(disp.confidence_factor * 100, 0)}%
            <span className="analysis-sub-label">Konfidenz</span>
          </div>
          <div className="analysis-detail">
            <span className="analysis-metric">
              Std-Abweichung: {formatNumber(disp.pillar_std, 1)}
            </span>
            {disp.high_dispersion && (
              <span className="dispersion-warning">Hohe Divergenz</span>
            )}
          </div>
          <div className="analysis-explanation">
            {disp.high_dispersion
              ? 'Pillars divergieren stark - Signal weniger zuverlaessig'
              : 'Pillars zeigen aehnliche Richtung - starkes Signal'}
          </div>
        </div>

        {/* Volatility Regime */}
        <div className="sentiment-analysis-card">
          <h3>Volatilitaets-Regime</h3>
          {vol ? (
            <>
              <div className="analysis-main-value">
                <span
                  className={`vol-regime-badge vol-${vol.regime.toLowerCase()}`}
                >
                  {vol.regime}
                </span>
              </div>
              <div className="analysis-detail">
                <span className="analysis-metric">
                  Vol 20d: {formatNumber(vol.realized_vol_20d * 100, 1)}%
                </span>
                <span className="analysis-metric">
                  Vol 120d: {formatNumber(vol.avg_vol_120d * 100, 1)}%
                </span>
                <span className="analysis-metric">
                  Ratio: {formatNumber(vol.vol_ratio, 2)}x
                </span>
              </div>
              <div className="analysis-explanation">
                Skalierung: {formatNumber(vol.scaling_factor, 1)}x
                {vol.regime === 'HIGH'
                  ? ' (Multiplier-Range komprimiert)'
                  : vol.regime === 'LOW'
                    ? ' (Multiplier-Range erweitert)'
                    : ' (Standard)'}
              </div>
            </>
          ) : (
            <div className="analysis-unavailable">
              Nicht genuegend Daten (min. 120 Tage)
            </div>
          )}
        </div>
      </div>

      {/* Disclaimer */}
      <div className="sentiment-disclaimer">
        Indikativ, keine Handelsempfehlung. Sentiment Score basiert auf 5
        unabhaengigen Datenquellen und ersetzt keine eigene Analyse.
        Kaufgroessen-Multiplikator als Orientierung.
      </div>
    </div>
  );
};

export default Sentiment;
