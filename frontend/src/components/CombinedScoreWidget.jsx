/**
 * CombinedScoreWidget - Compact Combined Score hero banner for Dashboard
 *
 * Displays action label, size multiplier, and unified score bar.
 * Fetches data independently via useQuery with same queryKey as CombinedScore.jsx
 * (TanStack Query cache sharing). Clicking navigates to full Combined Score page.
 */
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getCombinedScore, getSettings } from '../api/client';
import { useChartTheme } from '../hooks/useChartTheme';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import { formatNumber } from '../utils/formatters';
import './CombinedScoreWidget.css';

const CombinedScoreWidget = () => {
  const { userId } = useUser();
  const { symbol } = useSymbol();
  const theme = useChartTheme();
  const navigate = useNavigate();

  const ACTION_COLOR_MAP = {
    'Aggressiv kaufen': theme.actionStrongBuy,
    'Kaufen': theme.actionBuy,
    'Leicht akkumulieren': theme.actionLeanBuy,
    'Abwarten': theme.actionHold,
    'Leicht reduzieren': theme.actionLeanSell,
    'Verkaufen': theme.actionSell,
    'Aggressiv verkaufen': theme.actionStrongSell,
  };

  const { data: settings } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
  });

  const interval = settings?.macro_signal_interval || '15';

  const { data, isLoading, error } = useQuery({
    queryKey: ['combined-score', symbol, userId, interval],
    queryFn: () => getCombinedScore(userId, interval, symbol),
    refetchInterval: interval === '1' ? 30000 : interval === '5' ? 45000 : 60000,
  });

  if (isLoading) {
    return (
      <div className="combined-widget combined-widget-loading">
        <div className="widget-loading-text">Lade Combined Score...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="combined-widget combined-widget-error">
        <span className="widget-error-text">Combined Score nicht verfuegbar</span>
      </div>
    );
  }

  if (!data) return null;

  const actionColor = ACTION_COLOR_MAP[data.action] || theme.actionHold;
  const scorePosition = ((data.unified_score + 100) / 200) * 100;

  const multiplierColor = data.size_multiplier > 1
    ? theme.profit
    : data.size_multiplier < 1
      ? theme.loss
      : theme.textMuted;

  return (
    <div
      className="combined-widget"
      onClick={() => navigate(`/s/${symbol}/combined`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/s/${symbol}/combined`); }}
    >
      <div className="widget-action-banner" style={{ '--action-color': actionColor }}>
        <div className="widget-action-main">
          <span className="widget-action-label" style={{ color: actionColor }}>
            {data.action}
          </span>
          <span className="widget-multiplier" style={{ color: multiplierColor }}>
            {formatNumber(data.size_multiplier, 2)}x
          </span>
        </div>

        <div className="widget-score-bar-section">
          <div className="widget-score-labels">
            <span>-100</span>
            <span>Sell</span>
            <span>0</span>
            <span>Buy</span>
            <span>+100</span>
          </div>
          <div className="widget-score-track">
            <div className="widget-score-center-mark" />
            <div className="widget-score-threshold" style={{ left: '20%' }} title="-60" />
            <div className="widget-score-threshold" style={{ left: '35%' }} title="-30" />
            <div className="widget-score-threshold" style={{ left: '45%' }} title="-10" />
            <div className="widget-score-threshold" style={{ left: '55%' }} title="+10" />
            <div className="widget-score-threshold" style={{ left: '65%' }} title="+30" />
            <div className="widget-score-threshold" style={{ left: '80%' }} title="+60" />
            <div
              className="widget-score-indicator"
              style={{
                left: `${Math.max(2, Math.min(98, scorePosition))}%`,
                backgroundColor: actionColor,
              }}
            />
          </div>
          <div className="widget-score-value">
            Score: <strong>{data.unified_score > 0 ? '+' : ''}{formatNumber(data.unified_score, 1)}</strong>
            {' '}| Intensity: <strong>{formatNumber(data.intensity * 100, 0)}%</strong>
          </div>
        </div>
      </div>

      <div className="widget-details-hint">Details anzeigen &rsaquo;</div>
    </div>
  );
};

export default CombinedScoreWidget;
