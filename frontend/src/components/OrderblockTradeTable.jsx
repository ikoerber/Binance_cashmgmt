import { formatEUR, formatNumber } from '../utils/formatters';
import OrderblockChart from './OrderblockChart';

const SORT_ICON = { asc: ' \u25B2', desc: ' \u25BC' };

const SortIcon = ({ sortConfig, col }) => {
  if (sortConfig.key !== col) return <span className="sort-icon">{SORT_ICON.asc}</span>;
  return <span className="sort-icon sort-active">{SORT_ICON[sortConfig.dir]}</span>;
};

const OrderblockTradeTable = ({
  trades,
  sortedTrades,
  showTrades,
  onToggleTrades,
  selectedTradeRow,
  onSelectTradeRow,
  tradeSortConfig,
  onSort,
  selectedTradeZone,
  tradeCandleData,
  tradeCandlesLoading,
}) => {
  if (trades.length === 0) return null;

  return (
    <div className="ob-trades-section">
      <button
        className="btn-ob-trades-toggle"
        onClick={onToggleTrades}
      >
        {showTrades ? 'Trade-Details ausblenden' : `Trade-Details anzeigen (${trades.length})`}
      </button>
      {showTrades && (
        <div className="ob-table-container">
          <table className="ob-table">
            <thead>
              <tr>
                <th onClick={() => onSort('outcome')}>
                  Outcome <SortIcon sortConfig={tradeSortConfig} col="outcome" />
                </th>
                <th onClick={() => onSort('conviction')}>
                  Conviction <SortIcon sortConfig={tradeSortConfig} col="conviction" />
                </th>
                <th onClick={() => onSort('direction')}>
                  Direction <SortIcon sortConfig={tradeSortConfig} col="direction" />
                </th>
                <th>Entry / Stop / Target</th>
                <th onClick={() => onSort('penetration_depth_pct')}>
                  Penetration <SortIcon sortConfig={tradeSortConfig} col="penetration_depth_pct" />
                </th>
                <th onClick={() => onSort('holding_duration_candles')}>
                  Duration <SortIcon sortConfig={tradeSortConfig} col="holding_duration_candles" />
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedTrades.map((trade) => (
                <tr
                  key={`${trade.ob_id}_${trade.entry_timestamp}`}
                  className={`ob-zone-row ${selectedTradeRow?.ob_id === trade.ob_id ? 'ob-zone-row-selected' : ''}`}
                  onClick={() => onSelectTradeRow(selectedTradeRow?.ob_id === trade.ob_id ? null : trade)}
                >
                  <td>
                    <span className={`ob-badge outcome-${trade.outcome.toLowerCase()}`}>
                      {trade.outcome}
                    </span>
                  </td>
                  <td>
                    <span className={`ob-badge conv-${trade.conviction.toLowerCase()}`}>
                      {trade.conviction}
                    </span>
                  </td>
                  <td>
                    <span className={`ob-badge dir-${trade.direction.toLowerCase()}`}>
                      {trade.direction === 'BULLISH' ? '\u2191' : '\u2193'}
                    </span>
                  </td>
                  <td>
                    <div className="cell-mono">E: {formatEUR(trade.entry_edge)}</div>
                    <div className="cell-mono cell-secondary">S: {formatEUR(trade.stop_edge)}</div>
                    <div className="cell-mono cell-secondary">T: {formatEUR(trade.target)}</div>
                  </td>
                  <td>{trade.penetration_depth_pct != null ? `${formatNumber(trade.penetration_depth_pct, 1)}%` : '-'}</td>
                  <td>{trade.holding_duration_candles != null ? `${trade.holding_duration_candles} Kerzen` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showTrades && selectedTradeRow && (
        <OrderblockChart
          candles={tradeCandleData?.candles || []}
          zone={selectedTradeZone}
          trade={selectedTradeRow}
          isLoading={tradeCandlesLoading}
        />
      )}
    </div>
  );
};

export default OrderblockTradeTable;
