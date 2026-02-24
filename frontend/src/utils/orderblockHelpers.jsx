const SORT_ICON = { asc: ' \u25B2', desc: ' \u25BC' };

const SortIcon = ({ sortConfig, col }) => {
  if (sortConfig.key !== col) return <span className="sort-icon">{SORT_ICON.asc}</span>;
  return <span className="sort-icon sort-active">{SORT_ICON[sortConfig.dir]}</span>;
};

const getScoreGradient = (score, theme) => {
  const s = parseFloat(score) || 0;
  if (!theme) {
    // Fallback for any callers that don't pass theme yet
    if (s <= 25) return 'linear-gradient(90deg, #94a3b8, #cbd5e1)';
    if (s <= 50) return 'linear-gradient(90deg, #60a5fa, #3b82f6)';
    if (s <= 75) return 'linear-gradient(90deg, #fbbf24, #d97706)';
    return 'linear-gradient(90deg, #a855f7, #7c3aed)';
  }
  if (s <= 25) return `linear-gradient(90deg, ${theme.gradientScoreLowStart}, ${theme.gradientScoreLowEnd})`;
  if (s <= 50) return `linear-gradient(90deg, ${theme.gradientScoreMidStart}, ${theme.gradientScoreMidEnd})`;
  if (s <= 75) return `linear-gradient(90deg, ${theme.gradientScoreHighStart}, ${theme.gradientScoreHighEnd})`;
  return `linear-gradient(90deg, ${theme.gradientScoreTopStart}, ${theme.gradientScoreTopEnd})`;
};

const zoneDistance = (zone, mp) => {
  const top = parseFloat(zone.zone_top) || 0;
  const bottom = parseFloat(zone.zone_bottom) || 0;
  if (mp >= bottom && mp <= top) return 0;
  return Math.min(Math.abs(mp - top), Math.abs(mp - bottom));
};

export { SORT_ICON, SortIcon, getScoreGradient, zoneDistance };
