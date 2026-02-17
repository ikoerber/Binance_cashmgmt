import { formatEUR, formatDate, formatTime, formatNumber } from '../utils/formatters';

const SORT_ICON = { asc: ' \u25B2', desc: ' \u25BC' };

const SortIcon = ({ sortConfig, col }) => {
  if (sortConfig.key !== col) return <span className="sort-icon">{SORT_ICON.asc}</span>;
  return <span className="sort-icon sort-active">{SORT_ICON[sortConfig.dir]}</span>;
};

const getScoreGradient = (score) => {
  const s = parseFloat(score) || 0;
  if (s <= 25) return 'linear-gradient(90deg, #94a3b8, #cbd5e1)';
  if (s <= 50) return 'linear-gradient(90deg, #60a5fa, #3b82f6)';
  if (s <= 75) return 'linear-gradient(90deg, #fbbf24, #d97706)';
  return 'linear-gradient(90deg, #a855f7, #7c3aed)';
};

const zoneDistance = (zone, mp) => {
  const top = parseFloat(zone.zone_top) || 0;
  const bottom = parseFloat(zone.zone_bottom) || 0;
  if (mp >= bottom && mp <= top) return 0;
  return Math.min(Math.abs(mp - top), Math.abs(mp - bottom));
};

const OrderblockZoneTable = ({
  sortedZones,
  selectedZone,
  onSelectZone,
  zoneSortConfig,
  onSort,
  marketPrice,
}) => {
  if (sortedZones.length === 0) return null;

  return (
    <div className="ob-table-container">
      <table className="ob-table">
        <thead>
          <tr>
            <th onClick={() => onSort('direction')}>
              Direction <SortIcon sortConfig={zoneSortConfig} col="direction" />
            </th>
            <th onClick={() => onSort('state')}>
              State <SortIcon sortConfig={zoneSortConfig} col="state" />
            </th>
            <th onClick={() => onSort('conviction')}>
              Conviction <SortIcon sortConfig={zoneSortConfig} col="conviction" />
            </th>
            <th onClick={() => onSort('category')}>
              Category <SortIcon sortConfig={zoneSortConfig} col="category" />
            </th>
            <th onClick={() => onSort('conviction_score')}>
              Score <SortIcon sortConfig={zoneSortConfig} col="conviction_score" />
            </th>
            <th onClick={() => onSort('has_liquidity_sweep')}>
              Sweep <SortIcon sortConfig={zoneSortConfig} col="has_liquidity_sweep" />
            </th>
            <th onClick={() => onSort('confluence_label')}>
              Confluence <SortIcon sortConfig={zoneSortConfig} col="confluence_label" />
            </th>
            <th onClick={() => onSort('zone_top')}>
              Zone Range <SortIcon sortConfig={zoneSortConfig} col="zone_top" />
            </th>
            <th onClick={() => onSort('price_distance')}>
              Distanz <SortIcon sortConfig={zoneSortConfig} col="price_distance" />
            </th>
            <th onClick={() => onSort('formed_at')}>
              Formed At <SortIcon sortConfig={zoneSortConfig} col="formed_at" />
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedZones.map(zone => (
            <tr
              key={zone.id}
              className={`ob-zone-row ${selectedZone?.id === zone.id ? 'ob-zone-row-selected' : ''}`}
              onClick={() => onSelectZone(selectedZone?.id === zone.id ? null : zone)}
            >
              <td>
                <span className={`ob-badge dir-${zone.direction.toLowerCase()}`}>
                  {zone.direction === 'BULLISH' ? '\u2191 Bull' : '\u2193 Bear'}
                </span>
              </td>
              <td>
                <span className={`ob-badge state-${zone.state.toLowerCase()}`}>
                  {zone.state}
                </span>
              </td>
              <td>
                <span className={`ob-badge conv-${zone.conviction.toLowerCase()}`}>
                  {zone.conviction}
                </span>
              </td>
              <td>
                <span className={`ob-badge cat-${(zone.category || 'unclassified').toLowerCase()}`}>
                  {zone.category || 'N/A'}
                </span>
              </td>
              <td>
                <div className="ob-score-cell">
                  <span className="ob-score-value">{formatNumber(zone.conviction_score, 1)}</span>
                  <div className="ob-score-bar-track">
                    <div
                      className="ob-score-bar-fill"
                      style={{
                        width: `${parseFloat(zone.conviction_score) || 0}%`,
                        background: getScoreGradient(zone.conviction_score),
                      }}
                    />
                  </div>
                </div>
              </td>
              <td>
                {zone.has_liquidity_sweep ? (
                  <span className="ob-badge sweep-yes" title={zone.liquidity_sweep_level ? `Level: ${formatEUR(zone.liquidity_sweep_level)}` : ''}>
                    Sweep
                  </span>
                ) : (
                  <span className="ob-badge sweep-no">&ndash;</span>
                )}
              </td>
              <td>
                {zone.confluence_label ? (
                  <span className={`ob-badge confl-${zone.confluence_label.toLowerCase().replace(/_/g, '-')}`}>
                    {zone.confluence_label === 'STRONG_CONTRARIAN' ? 'Strong'
                      : zone.confluence_label === 'MODERATE_CONTRARIAN' ? 'Moderate'
                      : zone.confluence_label === 'ADVERSE' ? 'Adverse'
                      : 'Neutral'}
                  </span>
                ) : (
                  <span className="ob-badge confl-na">N/A</span>
                )}
              </td>
              <td>
                <div className="cell-mono">{formatEUR(zone.zone_top)}</div>
                <div className="cell-secondary">{formatEUR(zone.zone_bottom)}</div>
              </td>
              <td>
                {marketPrice ? (
                  <span className="cell-mono">
                    {formatEUR(zoneDistance(zone, marketPrice))}
                  </span>
                ) : '\u2014'}
              </td>
              <td>{formatDate(zone.formed_at)} {formatTime(zone.formed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default OrderblockZoneTable;
