import { formatNumber } from '../utils/formatters';

const getScoreGradient = (score) => {
  const s = parseFloat(score) || 0;
  if (s <= 25) return 'linear-gradient(90deg, #94a3b8, #cbd5e1)';
  if (s <= 50) return 'linear-gradient(90deg, #60a5fa, #3b82f6)';
  if (s <= 75) return 'linear-gradient(90deg, #fbbf24, #d97706)';
  return 'linear-gradient(90deg, #a855f7, #7c3aed)';
};

const OrderblockKPIs = ({ allZones, metrics, analyzeResult }) => {
  const unmitCount = allZones.filter(z => z.state === 'UNMITIGATED').length;
  const hcCount = allZones.filter(z => z.is_high_conviction_zscore).length;
  const avgScore = allZones.length > 0
    ? (allZones.reduce((s, z) => s + (parseFloat(z.conviction_score) || 0), 0) / allZones.length)
    : 0;

  if (allZones.length === 0 && !metrics) return null;

  const strongCount = allZones.filter(z => z.confluence_label === 'STRONG_CONTRARIAN').length;
  const sentimentScore = analyzeResult?.meta?.sentiment_score;

  return (
    <div className="ob-kpi-grid">
      <div className="ob-kpi-card">
        <h3>Total Zones</h3>
        <div className="ob-kpi-value">{allZones.length}</div>
        <div className="ob-kpi-sub">{unmitCount} aktiv (Unmitigated)</div>
      </div>
      {metrics && (
        <div className="ob-kpi-card ob-kpi-bordered-green">
          <h3>Hit Rate</h3>
          <div className="ob-kpi-value ob-kpi-accent">
            {metrics.hit_rate != null ? `${formatNumber(parseFloat(metrics.hit_rate) * 100, 1)}%` : 'N/A'}
          </div>
          <div className="ob-kpi-sub">
            {metrics.hits} Hits / {metrics.hits + metrics.misses} abgeschlossen
          </div>
        </div>
      )}
      <div className="ob-kpi-card ob-kpi-bordered-amber">
        <h3>High Conviction</h3>
        <div className="ob-kpi-value">{hcCount}</div>
        <div className="ob-kpi-sub">Z-Score &gt; Threshold</div>
      </div>
      <div className="ob-kpi-card ob-kpi-bordered-blue">
        <h3>Avg Score</h3>
        <div className="ob-kpi-value">{formatNumber(avgScore, 1)}</div>
        <div className="ob-kpi-bar-track">
          <div
            className="ob-kpi-bar-fill"
            style={{ width: `${avgScore}%`, background: getScoreGradient(avgScore) }}
          />
        </div>
      </div>
      {(strongCount > 0 || sentimentScore != null) && (
        <div className="ob-kpi-card ob-kpi-bordered-purple">
          <h3>Sentiment Confluence</h3>
          <div className="ob-kpi-value">{strongCount} Strong</div>
          <div className="ob-kpi-sub">
            {sentimentScore != null
              ? `Sentiment: ${formatNumber(sentimentScore, 0)}/100`
              : 'Sentiment: N/A'}
          </div>
        </div>
      )}
    </div>
  );
};

export default OrderblockKPIs;
