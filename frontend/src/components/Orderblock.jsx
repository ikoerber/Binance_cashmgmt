import { useState, useMemo, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import {
  getSettings, analyzeOrderblocks, getOrderblockZones, deleteOrderblockZones,
  getOrderblockBacktestRuns, getOrderblockCandles,
} from '../api/client';
import { formatEUR, formatDate, formatTime, formatNumber } from '../utils/formatters';
import OrderblockChart from './OrderblockChart';
import './Orderblock.css';

// ─── Helpers ───

const getScoreGradient = (score) => {
  const s = parseFloat(score) || 0;
  if (s <= 25) return 'linear-gradient(90deg, #94a3b8, #cbd5e1)';
  if (s <= 50) return 'linear-gradient(90deg, #60a5fa, #3b82f6)';
  if (s <= 75) return 'linear-gradient(90deg, #fbbf24, #d97706)';
  return 'linear-gradient(90deg, #a855f7, #7c3aed)';
};

const SORT_ICON = { asc: ' \u25B2', desc: ' \u25BC' };

const Orderblock = ({ userId = 'user_123' }) => {
  const queryClient = useQueryClient();

  // ─── State ───
  const [interval, setInterval_] = useState('4h');
  const [months, setMonths] = useState(6);
  const [zoneStateFilter, setZoneStateFilter] = useState('UNMITIGATED');
  const [convictionFilter, setConvictionFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [zoneSortConfig, setZoneSortConfig] = useState({ key: 'formed_at', dir: 'desc' });
  const [tradeSortConfig, setTradeSortConfig] = useState({ key: null, dir: 'asc' });
  const [analyzeResult, setAnalyzeResult] = useState(null);
  const [message, setMessage] = useState(null);
  const [showTrades, setShowTrades] = useState(false);
  const [selectedZone, setSelectedZone] = useState(null);
  const [selectedTradeRow, setSelectedTradeRow] = useState(null);

  const showMsg = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  // ─── Queries ───

  const { data: settings } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
  });

  useEffect(() => {
    if (settings?.ob_interval) {
      setInterval_(settings.ob_interval);
    }
  }, [settings?.ob_interval]);

  const { data: zonesData, isLoading: zonesLoading } = useQuery({
    queryKey: ['ob-zones', userId, interval],
    queryFn: () => getOrderblockZones(userId, { interval }),
  });

  const { data: runsData } = useQuery({
    queryKey: ['ob-backtest-runs', userId],
    queryFn: () => getOrderblockBacktestRuns(userId),
  });

  const { data: candleData, isLoading: candlesLoading } = useQuery({
    queryKey: ['ob-candles', userId, selectedZone?.id, interval],
    queryFn: () => getOrderblockCandles(userId, {
      interval,
      zoneId: selectedZone.id,
    }),
    enabled: !!selectedZone,
    staleTime: 5 * 60 * 1000,
  });

  // ─── Mutations ───

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeOrderblocks(userId, { interval, months }),
    onSuccess: (data) => {
      setAnalyzeResult(data);
      queryClient.invalidateQueries({ queryKey: ['ob-zones', userId] });
      queryClient.invalidateQueries({ queryKey: ['ob-backtest-runs', userId] });
      showMsg('success', `Analyse abgeschlossen: ${data.zones?.length || 0} Zonen, ${data.trades?.length || 0} Trades simuliert.`);
    },
    onError: (err) => showMsg('error', err.response?.data?.detail || err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteOrderblockZones(userId, { interval }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['ob-zones', userId] });
      setAnalyzeResult(null);
      showMsg('success', `${data.deleted || 0} Zonen gelöscht.`);
    },
    onError: (err) => showMsg('error', err.response?.data?.detail || err.message),
  });

  // ─── Derived Data ───

  const allZones = zonesData?.zones || [];

  const filteredZones = useMemo(() => {
    let z = allZones;
    if (zoneStateFilter) z = z.filter(zone => zone.state === zoneStateFilter);
    if (convictionFilter) z = z.filter(zone => zone.conviction === convictionFilter);
    if (categoryFilter) z = z.filter(zone => zone.category === categoryFilter);
    return z;
  }, [allZones, zoneStateFilter, convictionFilter, categoryFilter]);

  const sortedZones = useMemo(() => {
    if (!zoneSortConfig.key) return filteredZones;
    return [...filteredZones].sort((a, b) => {
      let av = a[zoneSortConfig.key], bv = b[zoneSortConfig.key];
      if (zoneSortConfig.key === 'conviction_score' || zoneSortConfig.key === 'zone_top') {
        av = parseFloat(av) || 0; bv = parseFloat(bv) || 0;
      }
      if (av < bv) return zoneSortConfig.dir === 'asc' ? -1 : 1;
      if (av > bv) return zoneSortConfig.dir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filteredZones, zoneSortConfig]);

  const trades = analyzeResult?.trades || [];
  const sortedTrades = useMemo(() => {
    if (!tradeSortConfig.key) return trades;
    return [...trades].sort((a, b) => {
      let av = a[tradeSortConfig.key], bv = b[tradeSortConfig.key];
      if (['penetration_depth_pct', 'holding_duration_candles', 'conviction_score'].includes(tradeSortConfig.key)) {
        av = parseFloat(av) || 0; bv = parseFloat(bv) || 0;
      }
      if (av < bv) return tradeSortConfig.dir === 'asc' ? -1 : 1;
      if (av > bv) return tradeSortConfig.dir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [trades, tradeSortConfig]);

  // ─── Selected Trade: matchende Zone + Candle-Fetch ───
  const selectedTradeZone = useMemo(() => {
    if (!selectedTradeRow) return null;
    return allZones.find(z => z.id === selectedTradeRow.ob_id) || null;
  }, [selectedTradeRow, allZones]);

  const { data: tradeCandleData, isLoading: tradeCandlesLoading } = useQuery({
    queryKey: ['ob-candles-trade', userId, selectedTradeRow?.ob_id, selectedTradeRow?.entry_timestamp, interval],
    queryFn: () => getOrderblockCandles(userId, {
      interval,
      startTime: selectedTradeRow.entry_timestamp,
      endTime: selectedTradeRow.exit_timestamp || selectedTradeRow.entry_timestamp,
    }),
    enabled: !!selectedTradeRow?.entry_timestamp,
    staleTime: 5 * 60 * 1000,
  });

  // ─── Selected Zone: matchender Trade ───
  const selectedTrade = useMemo(() => {
    if (!selectedZone || !trades.length) return null;
    return trades.find(t => t.ob_id === selectedZone.id) || null;
  }, [selectedZone, trades]);

  // Reset Selections bei Interval-/Filter-Aenderung
  useEffect(() => {
    setSelectedZone(null);
    setSelectedTradeRow(null);
  }, [interval, zoneStateFilter, convictionFilter, categoryFilter]);

  // ─── Zone KPIs ───
  const unmitCount = allZones.filter(z => z.state === 'UNMITIGATED').length;
  const hcCount = allZones.filter(z => z.is_high_conviction_zscore).length;
  const avgScore = allZones.length > 0
    ? (allZones.reduce((s, z) => s + (parseFloat(z.conviction_score) || 0), 0) / allZones.length)
    : 0;

  // ─── Chart Data ───
  const stateChartData = [
    { name: 'Unmitigated', count: allZones.filter(z => z.state === 'UNMITIGATED').length, fill: '#16a34a' },
    { name: 'Mitigated', count: allZones.filter(z => z.state === 'MITIGATED').length, fill: '#94a3b8' },
    { name: 'Invalid', count: allZones.filter(z => z.state === 'INVALID').length, fill: '#dc2626' },
  ];

  const metrics = analyzeResult?.metrics;
  const convBreakdown = metrics?.conviction_breakdown || [];
  const convChartData = convBreakdown.map(cb => ({
    level: cb.level,
    Hits: cb.hits,
    Misses: cb.misses,
    Expired: cb.expired || 0,
  }));

  // ─── Sort Handlers ───
  const handleZoneSort = (key) => {
    setZoneSortConfig(prev => ({
      key,
      dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc',
    }));
  };
  const handleTradeSort = (key) => {
    setTradeSortConfig(prev => ({
      key,
      dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc',
    }));
  };

  const SortIcon = ({ sortConfig, col }) => {
    if (sortConfig.key !== col) return <span className="sort-icon">{SORT_ICON.asc}</span>;
    return <span className="sort-icon sort-active">{SORT_ICON[sortConfig.dir]}</span>;
  };

  // ─── Render ───
  const runs = runsData?.runs || [];

  return (
    <div className="orderblock-container">
      <div className="ob-header">
        <h2>Orderblock Detection</h2>
        <p>Institutionelle Preiszonen erkennen, validieren und backtesten — in einem Schritt.</p>
      </div>

      <div className="ob-explainer">
        <details>
          <summary>Was sind Orderblocks?</summary>
          <div className="ob-explainer-content">
            <p>
              <strong>Orderblocks</strong> sind Preiszonen, in denen institutionelle Marktteilnehmer
              grosse Orders platziert haben. Wenn der Preis zu diesen Zonen zurueckkehrt, reagiert
              er haeufig — weil dort noch offenes Interesse (unerfuellte Orders) liegt.
            </p>
            <div className="ob-explainer-phases">
              <h4>5-Phasen-Validierung</h4>
              <ol>
                <li><strong>Formation</strong> — Basiskerze mit hohem Volumen identifizieren</li>
                <li><strong>Displacement</strong> — Starke Bewegung weg von der Zone (ATR-basiert)</li>
                <li><strong>Fair Value Gap</strong> — 3-Kerzen-Imbalance bestaetigt institutionelles Interesse</li>
                <li><strong>Structure Break</strong> — Fraktal-Swing-High/Low wird durchbrochen (BOS)</li>
                <li><strong>State Management</strong> — Zone aktiv bis Preis sie erreicht (Mitigation) oder invalidiert</li>
              </ol>
            </div>
            <div className="ob-explainer-grid">
              <div className="ob-explainer-item">
                <span className="ob-badge dir-bullish">Bullish OB</span>
                <span>Letzte Abwaertskerze vor starkem Anstieg — Kaufzone</span>
              </div>
              <div className="ob-explainer-item">
                <span className="ob-badge dir-bearish">Bearish OB</span>
                <span>Letzte Aufwaertskerze vor starkem Abfall — Verkaufszone</span>
              </div>
            </div>
            <div className="ob-explainer-conviction">
              <h4>Conviction-Stufen</h4>
              <p>
                Jede Zone erhaelt einen Composite Conviction Score (0-100), berechnet aus
                4 gleichgewichteten Komponenten (je 25%):
              </p>
              <ul className="ob-explainer-components">
                <li><strong>Volume Percentile</strong> — Wie extrem war das Volumen? (Cont: robust gegen Heavy Tails)</li>
                <li><strong>Volume Z-Score</strong> — Standardabweichungen ueber dem Mittel (50-Kerzen Lookback)</li>
                <li><strong>OFI Divergenz</strong> — Order Flow Imbalance zwischen Formation und Impuls (Bouchaud)</li>
                <li><strong>Impulse Intensity</strong> — Kerzen-Koerper-Staerke × Volumen-Gewicht</li>
              </ul>
            </div>
          </div>
        </details>
      </div>

      {message && (
        <div className={`ob-message ob-message-${message.type}`}>
          {message.text}
          <button className="ob-message-close" onClick={() => setMessage(null)}>&times;</button>
        </div>
      )}

      {/* ─── Action Bar ─── */}
      <div className="ob-action-bar">
        <button
          className="btn-ob-action"
          onClick={() => analyzeMutation.mutate()}
          disabled={analyzeMutation.isPending}
        >
          {analyzeMutation.isPending ? 'Analysiere...' : 'Analyse starten'}
        </button>
        {allZones.length > 0 && (
          <button
            className="btn-ob-action btn-ob-delete"
            onClick={() => { if (window.confirm(`Alle ${allZones.length} Zonen (${interval}) löschen?`)) deleteMutation.mutate(); }}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Lösche...' : 'Alle Zonen löschen'}
          </button>
        )}
        <div className="ob-param-group">
          <label>Interval</label>
          <select value={interval} onChange={e => setInterval_(e.target.value)}>
            <option value="1h">1 Stunde</option>
            <option value="4h">4 Stunden</option>
            <option value="1d">1 Tag</option>
          </select>
        </div>
        <div className="ob-param-group">
          <label>Lookback</label>
          <select value={months} onChange={e => setMonths(Number(e.target.value))}>
            <option value={3}>3 Monate</option>
            <option value={6}>6 Monate</option>
            <option value={12}>12 Monate</option>
            <option value={24}>24 Monate</option>
          </select>
        </div>
      </div>

      {/* ─── KPI Cards (Zones + Backtest combined) ─── */}
      {(allZones.length > 0 || metrics) && (
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
        </div>
      )}

      {/* ─── Filters ─── */}
      {allZones.length > 0 && (
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
          <button
            className="btn-ob-filter-reset"
            onClick={() => { setZoneStateFilter('UNMITIGATED'); setConvictionFilter(''); setCategoryFilter(''); }}
          >
            Reset
          </button>
        </div>
      )}

      {/* ─── Charts ─── */}
      {(allZones.length > 0 || convChartData.length > 0) && (
        <div className="ob-charts-row">
          {allZones.length > 0 && (
            <div className="ob-chart-section ob-chart-half">
              <h3>Zone States</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={stateChartData} barSize={48}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                  <YAxis stroke="#64748b" fontSize={12} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {stateChartData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          {convChartData.length > 0 && (
            <div className="ob-chart-section ob-chart-half">
              <h3>Conviction Breakdown</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={convChartData} barGap={2}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="level" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }} />
                  <Legend />
                  <Bar dataKey="Hits" fill="#16a34a" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Misses" fill="#dc2626" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Expired" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* ─── Zone Table ─── */}
      {zonesLoading ? (
        <div className="ob-loading">Lade Zonen...</div>
      ) : sortedZones.length > 0 ? (
        <div className="ob-table-container">
          <table className="ob-table">
            <thead>
              <tr>
                <th onClick={() => handleZoneSort('direction')}>
                  Direction <SortIcon sortConfig={zoneSortConfig} col="direction" />
                </th>
                <th onClick={() => handleZoneSort('state')}>
                  State <SortIcon sortConfig={zoneSortConfig} col="state" />
                </th>
                <th onClick={() => handleZoneSort('conviction')}>
                  Conviction <SortIcon sortConfig={zoneSortConfig} col="conviction" />
                </th>
                <th onClick={() => handleZoneSort('category')}>
                  Category <SortIcon sortConfig={zoneSortConfig} col="category" />
                </th>
                <th onClick={() => handleZoneSort('conviction_score')}>
                  Score <SortIcon sortConfig={zoneSortConfig} col="conviction_score" />
                </th>
                <th onClick={() => handleZoneSort('zone_top')}>
                  Zone Range <SortIcon sortConfig={zoneSortConfig} col="zone_top" />
                </th>
                <th onClick={() => handleZoneSort('formed_at')}>
                  Formed At <SortIcon sortConfig={zoneSortConfig} col="formed_at" />
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedZones.map(zone => (
                <tr
                  key={zone.id}
                  className={`ob-zone-row ${selectedZone?.id === zone.id ? 'ob-zone-row-selected' : ''}`}
                  onClick={() => setSelectedZone(selectedZone?.id === zone.id ? null : zone)}
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
                    <div className="cell-mono">{formatEUR(zone.zone_top)}</div>
                    <div className="cell-secondary">{formatEUR(zone.zone_bottom)}</div>
                  </td>
                  <td>{formatDate(zone.formed_at)} {formatTime(zone.formed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* ─── Candlestick Chart (bei selektierter Zone) ─── */}
      {selectedZone && (
        <OrderblockChart
          candles={candleData?.candles || []}
          zone={selectedZone}
          trade={selectedTrade}
          isLoading={candlesLoading}
        />
      )}

      {!zonesLoading && sortedZones.length === 0 && (
        allZones.length === 0 && !analyzeMutation.isPending ? (
          <div className="ob-table-empty">
            Noch keine Zonen vorhanden. Starte eine Analyse um Orderblocks zu erkennen.
          </div>
        ) : filteredZones.length === 0 ? (
          <div className="ob-table-empty">
            Keine Zonen fuer die aktuelle Filterauswahl.
          </div>
        ) : null
      )}

      {/* ─── Trade Outcomes (collapsible) ─── */}
      {trades.length > 0 && (
        <div className="ob-trades-section">
          <button
            className="btn-ob-trades-toggle"
            onClick={() => setShowTrades(v => !v)}
          >
            {showTrades ? 'Trade-Details ausblenden' : `Trade-Details anzeigen (${trades.length})`}
          </button>
          {showTrades && (
            <div className="ob-table-container">
              <table className="ob-table">
                <thead>
                  <tr>
                    <th onClick={() => handleTradeSort('outcome')}>
                      Outcome <SortIcon sortConfig={tradeSortConfig} col="outcome" />
                    </th>
                    <th onClick={() => handleTradeSort('conviction')}>
                      Conviction <SortIcon sortConfig={tradeSortConfig} col="conviction" />
                    </th>
                    <th onClick={() => handleTradeSort('direction')}>
                      Direction <SortIcon sortConfig={tradeSortConfig} col="direction" />
                    </th>
                    <th>Entry / Stop / Target</th>
                    <th onClick={() => handleTradeSort('penetration_depth_pct')}>
                      Penetration <SortIcon sortConfig={tradeSortConfig} col="penetration_depth_pct" />
                    </th>
                    <th onClick={() => handleTradeSort('holding_duration_candles')}>
                      Duration <SortIcon sortConfig={tradeSortConfig} col="holding_duration_candles" />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedTrades.map((trade, idx) => (
                    <tr
                      key={idx}
                      className={`ob-zone-row ${selectedTradeRow?.ob_id === trade.ob_id ? 'ob-zone-row-selected' : ''}`}
                      onClick={() => setSelectedTradeRow(selectedTradeRow?.ob_id === trade.ob_id ? null : trade)}
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

          {/* ─── Trade Candlestick Chart ─── */}
          {showTrades && selectedTradeRow && (
            <OrderblockChart
              candles={tradeCandleData?.candles || []}
              zone={selectedTradeZone}
              trade={selectedTradeRow}
              isLoading={tradeCandlesLoading}
            />
          )}
        </div>
      )}

      {/* ─── Historical Runs ─── */}
      {runs.length > 0 && (
        <div className="ob-runs-section">
          <div className="ob-runs-header">
            <h3>Historische Analyse-Runs</h3>
          </div>
          <div className="ob-runs-list">
            {runs.map(run => (
              <div key={run.id} className="ob-run-card">
                <div className="ob-run-info">
                  <span className="ob-run-date">{formatDate(run.created_at)}</span>
                  <span className="ob-run-stats">
                    Zones: {run.total_zones} | Trades: {run.total_trades} | Hits: {run.hits}
                  </span>
                </div>
                <div className="ob-run-badges">
                  <span className="ob-run-interval-badge">{run.interval}</span>
                  <span className="ob-run-hitrate">
                    {run.hit_rate != null ? `${formatNumber(parseFloat(run.hit_rate) * 100, 1)}%` : 'N/A'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="ob-disclaimer">
        Orderblock Detection basiert auf historischen Preisdaten und stellt keine Anlageberatung dar.
        Vergangene Ergebnisse garantieren keine zukuenftigen Resultate.
      </div>
    </div>
  );
};

export default Orderblock;
