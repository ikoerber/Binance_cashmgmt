/**
 * useChartTheme - Shared chart color bridge hook
 *
 * Reads all chart-relevant CSS custom properties via getComputedStyle
 * and returns a plain JS object with resolved color strings.
 *
 * Used by: OrderblockChart.jsx, Orderblock.jsx, CombinedScore.jsx,
 *          Overview.jsx, orderblockHelpers.jsx
 *
 * Note: This is a plain function (not a React hook with state/effects).
 * Named useChartTheme by convention to match existing codebase pattern.
 */

const useChartTheme = () => {
  const style = getComputedStyle(document.documentElement);
  const get = (name, fallback) => style.getPropertyValue(name).trim() || fallback;

  return {
    // Layout
    bgCard: get('--color-bg-card', '#161822'),
    bgPage: get('--color-bg-page', '#0f1117'),
    textPrimary: get('--color-text-primary', '#e2e8f0'),
    textSecondary: get('--color-text-secondary', '#94a3b8'),
    textMuted: get('--color-text-muted', '#64748b'),

    // Borders / Grid
    border: get('--color-border', '#2e3348'),
    borderLight: get('--color-border-light', '#252838'),

    // Semantic
    profit: get('--color-profit', '#22c55e'),
    loss: get('--color-loss', '#ef4444'),
    profitBright: get('--color-profit-bright', '#4ade80'),

    // Accents
    accentOrderblock: get('--color-accent-orderblock', '#fbbf24'),
    accentAmber: get('--color-accent-amber', '#fbbf24'),
    accentBlue: get('--color-accent-blue', '#60a5fa'),

    // Chart palette (Recharts)
    chart1: get('--color-chart-1', '#818cf8'),
    chart2: get('--color-chart-2', '#fbbf24'),
    chart3: get('--color-chart-3', '#34d399'),
    chart4: get('--color-chart-4', '#f87171'),
    chart5: get('--color-chart-5', '#a78bfa'),

    // Action colors (CombinedScore)
    actionStrongBuy: get('--color-action-strong-buy', '#22c55e'),
    actionBuy: get('--color-action-buy', '#4ade80'),
    actionLeanBuy: get('--color-action-lean-buy', '#86efac'),
    actionHold: get('--color-action-hold', '#94a3b8'),
    actionLeanSell: get('--color-action-lean-sell', '#fbbf24'),
    actionSell: get('--color-action-sell', '#fb923c'),
    actionStrongSell: get('--color-action-strong-sell', '#ef4444'),

    // Score gradients (orderblockHelpers)
    gradientScoreLowStart: get('--color-gradient-score-low-start', '#94a3b8'),
    gradientScoreLowEnd: get('--color-gradient-score-low-end', '#cbd5e1'),
    gradientScoreMidStart: get('--color-gradient-score-mid-start', '#60a5fa'),
    gradientScoreMidEnd: get('--color-gradient-score-mid-end', '#93c5fd'),
    gradientScoreHighStart: get('--color-gradient-score-high-start', '#fbbf24'),
    gradientScoreHighEnd: get('--color-gradient-score-high-end', '#fcd34d'),
    gradientScoreTopStart: get('--color-gradient-score-top-start', '#a855f7'),
    gradientScoreTopEnd: get('--color-gradient-score-top-end', '#c084fc'),

    // Pillar gradients (CombinedScore)
    gradientPillarFearStart: get('--color-gradient-pillar-fear-start', '#ef4444'),
    gradientPillarFearEnd: get('--color-gradient-pillar-fear-end', '#fb923c'),
    gradientPillarCautionStart: get('--color-gradient-pillar-caution-start', '#fb923c'),
    gradientPillarCautionEnd: get('--color-gradient-pillar-caution-end', '#fbbf24'),
    gradientPillarNeutralStart: get('--color-gradient-pillar-neutral-start', '#94a3b8'),
    gradientPillarNeutralEnd: get('--color-gradient-pillar-neutral-end', '#cbd5e1'),
    gradientPillarGreedStart: get('--color-gradient-pillar-greed-start', '#4ade80'),
    gradientPillarGreedEnd: get('--color-gradient-pillar-greed-end', '#86efac'),
    gradientPillarExtremeStart: get('--color-gradient-pillar-extreme-start', '#22c55e'),
    gradientPillarExtremeEnd: get('--color-gradient-pillar-extreme-end', '#4ade80'),
  };
};

/**
 * hexToRgb - Converts hex color to RGB components string
 *
 * @param {string} hex - Hex color string (e.g., '#22c55e' or '#abc')
 * @returns {string} RGB components (e.g., '34, 197, 94') for use in rgba()
 */
const hexToRgb = (hex) => {
  const h = hex.replace('#', '');
  const full = h.length === 3
    ? h.split('').map(c => c + c).join('')
    : h;
  const r = parseInt(full.substring(0, 2), 16);
  const g = parseInt(full.substring(2, 4), 16);
  const b = parseInt(full.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
};

export { useChartTheme, hexToRgb };
