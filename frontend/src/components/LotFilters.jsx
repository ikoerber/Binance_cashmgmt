/**
 * LotFilters - Filter-Bar fuer TradeLots
 */
const LotFilters = ({
  statusFilter, setStatusFilter,
  fromDate, setFromDate,
  toDate, setToDate,
  orderFilter, setOrderFilter,
  showClosed, setShowClosed,
}) => {
  return (
    <div className="lots-filters">
      <div className="filter-group">
        <span className="filter-label">Order Nr.</span>
        <input
          type="text"
          value={orderFilter}
          onChange={(e) => setOrderFilter(e.target.value)}
          placeholder="Suchen..."
        />
      </div>
      <div className="filter-group">
        <span className="filter-label">Status</span>
        <select value={statusFilter || ''} onChange={(e) => setStatusFilter(e.target.value || null)}>
          <option value="">Alle</option>
          <option value="OPEN">Open</option>
          <option value="PARTIAL_CLOSED">Partial Closed</option>
          <option value="CLOSED">Closed</option>
        </select>
      </div>
      <label className="toggle-label">
        <span className="toggle-switch">
          <input
            type="checkbox"
            checked={showClosed}
            onChange={(e) => setShowClosed(e.target.checked)}
          />
          <span className="toggle-slider" />
        </span>
        Closed anzeigen
      </label>
      <div className="date-range">
        <div className="filter-group">
          <span className="filter-label">Von</span>
          <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
        </div>
        <span className="date-separator">&ndash;</span>
        <div className="filter-group">
          <span className="filter-label">Bis</span>
          <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
        </div>
      </div>
      {(statusFilter || fromDate || toDate || orderFilter) && (
        <button
          className="btn-reset-filters"
          onClick={() => { setStatusFilter(null); setFromDate(''); setToDate(''); setOrderFilter(''); }}
        >
          Filter zurücksetzen
        </button>
      )}
    </div>
  );
};

export default LotFilters;
