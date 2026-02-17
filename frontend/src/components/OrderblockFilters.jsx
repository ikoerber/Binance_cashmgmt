const OrderblockFilters = ({
  zoneStateFilter, setZoneStateFilter,
  convictionFilter, setConvictionFilter,
  categoryFilter, setCategoryFilter,
  confluenceFilter, setConfluenceFilter,
}) => (
  <div className="ob-filters">
    <div className="ob-filter-group">
      <label>State</label>
      <select value={zoneStateFilter} onChange={e => setZoneStateFilter(e.target.value)}>
        <option value="">Alle</option>
        <option value="UNMITIGATED">Unmitigated</option>
        <option value="MITIGATED">Mitigated</option>
        <option value="INVALID">Invalid</option>
      </select>
    </div>
    <div className="ob-filter-group">
      <label>Conviction</label>
      <select value={convictionFilter} onChange={e => setConvictionFilter(e.target.value)}>
        <option value="">Alle</option>
        <option value="LOW">Low</option>
        <option value="STANDARD">Standard</option>
        <option value="HIGH">High</option>
        <option value="INSTITUTIONAL">Institutional</option>
      </select>
    </div>
    <div className="ob-filter-group">
      <label>Category</label>
      <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}>
        <option value="">Alle</option>
        <option value="EXTREME">Extreme</option>
        <option value="DECISIONAL">Decisional</option>
        <option value="SMT">SMT</option>
        <option value="UNCLASSIFIED">Unclassified</option>
      </select>
    </div>
    <div className="ob-filter-group">
      <label>Confluence</label>
      <select value={confluenceFilter} onChange={e => setConfluenceFilter(e.target.value)}>
        <option value="">Alle</option>
        <option value="STRONG_CONTRARIAN">Strong Contrarian</option>
        <option value="MODERATE_CONTRARIAN">Moderate Contrarian</option>
        <option value="NEUTRAL">Neutral</option>
        <option value="ADVERSE">Adverse</option>
      </select>
    </div>
    <button
      className="btn-ob-filter-reset"
      onClick={() => { setZoneStateFilter(''); setConvictionFilter(''); setCategoryFilter(''); setConfluenceFilter(''); }}
    >
      Reset
    </button>
  </div>
);

export default OrderblockFilters;
