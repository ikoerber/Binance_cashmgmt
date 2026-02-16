import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import {
  getSettings, detectOrderblocks, getOrderblockZones,
  runOrderblockBacktest, getOrderblockBacktestRuns,
} from '../api/client';
import { formatEUR, formatDate, formatNumber } from '../utils/formatters';
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
  const [activeTab, setActiveTab] = useState('zones');
  const [interval, setInterval_] = useState('4h');
  const [months, setMonths] = useState(6);
  const [zoneStateFilter, setZoneStateFilter] = useState('');
  const [convictionFilter, setConvictionFilter] = useState('');
  const [zoneSortConfig, setZoneSortConfig] = useState({ key: 'formed_at', dir: 'desc' });
  const [tradeSortConfig, setTradeSortConfig] = useState({ key: null, dir: 'asc' });
  const [backtestResult, setBacktestResult] = useState(null);
  const [message, setMessage] = useState(null);

  const showMsg = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  // ─── Queries ───

  const { data: settings } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
  });

  const { data: zonesData, isLoading: zonesLoading } = useQuery({
    queryKey: ['ob-zones', userId, interval],
    queryFn: () => getOrderblockZones(userId, { interval }),
    enabled: activeTab === 'zones',
  });

  const { data: runsData } = useQuery({
    queryKey: ['ob-backtest-runs', userId],
    queryFn: () => getOrderblockBacktestRuns(userId),
    enabled: activeTab === 'backtest',
  });

  // ─── Mutations ───

  const detectMutation = useMutation({
    mutationFn: () => detectOrderblocks(userId, {
      interval: settings?.ob_interval || interval,
      months,
    }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['ob-zones', userId] });
      showMsg('success', `Detection abgeschlossen: ${data.zones?.length || 0} Zonen erkannt.`);
    },
    onError: (err) => showMsg('error', err.response?.data?.detail || err.message),
  });

  const backtestMutation = useMutation({
    mutationFn: () => runOrderblockBacktest(userId, {
      interval: settings?.ob_interval || interval,
      months,
    }),
    onSuccess: (data) => {
      setBacktestResult(data);
      queryClient.invalidateQueries({ queryKey: ['ob-backtest-runs', userId] });
      showMsg('success', `Backtest abgeschlossen: ${data.metrics?.total_trades || 0} Trades simuliert.`);
    },
    onError: (err) => showMsg('error', err.response?.data?.detail || err.message),
  });

  // ─── Derived Data ───

  const allZones = zonesData?.zones || [];

  const filteredZones = useMemo(() => {
    let z = allZones;
    if (zoneStateFilter) z = z.filter(zone => zone.state === zoneStateFilter);
    if (convictionFilter) z = z.filter(zone => zone.conviction === convictionFilter);
    return z;
  }, [allZones, zoneStateFilter, convictionFilter]);

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

  const trades = backtestResult?.trades || [];
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

  const convBreakdown = backtestResult?.metrics?.conviction_breakdown || [];
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
  const metrics = backtestResult?.metrics;
  const runs = runsData?.runs || [];

  return (
    <div className="orderblock-container">
      <div className="ob-header">
        <h2>Orderblock Detection</h2>
        <p>Institutionelle Preiszonen erkennen und backtesten.</p>
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
            <div className="ob-explainer-states">
              <h4>Zone States (Lebenszyklus)</h4>
              <div className="ob-explainer-grid">
                <div className="ob-explainer-item">
                  <span className="ob-badge state-unmitigated">Unmitigated</span>
                  <span>Zone wurde noch nicht erneut beruehrt — aktives Signal. Preis koennte bei Rueckkehr reagieren.</span>
                </div>
                <div className="ob-explainer-item">
                  <span className="ob-badge state-mitigated">Mitigated</span>
                  <span>Preis hat die Zone erreicht/durchquert. Offenes Interesse wurde absorbiert — Zone verbraucht.</span>
                </div>
                <div className="ob-explainer-item">
                  <span className="ob-badge state-invalid">Invalid</span>
                  <span>Gegenlaeufe Struktur hat die Zone invalidiert (z.B. neuer BOS in Gegenrichtung). Kein Signal mehr.</span>
                </div>
              </div>
              <p className="ob-explainer-state-flow">
                Ablauf: <strong>Unmitigated</strong> → Preis beruehrt Zone → <strong>Mitigated</strong> | Struktur bricht → <strong>Invalid</strong>
              </p>
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
              <div className="ob-explainer-level-grid">
                <div className="ob-explainer-level">
                  <span className="ob-badge conv-low">Low</span>
                  <span className="ob-explainer-level-range">Score &lt; 35</span>
                  <span>Schwaches Signal — wenig institutionelle Aktivitaet erkennbar</span>
                </div>
                <div className="ob-explainer-level">
                  <span className="ob-badge conv-standard">Standard</span>
                  <span className="ob-explainer-level-range">35 - 54</span>
                  <span>Normales Signal — moderate Anzeichen fuer Interesse</span>
                </div>
                <div className="ob-explainer-level">
                  <span className="ob-badge conv-high">High</span>
                  <span className="ob-explainer-level-range">55 - 74</span>
                  <span>Starkes Signal — deutliche institutionelle Spuren</span>
                </div>
                <div className="ob-explainer-level">
                  <span className="ob-badge conv-institutional">Institutional</span>
                  <span className="ob-explainer-level-range">75 - 100</span>
                  <span>Hoechste Stufe — alle Indikatoren zeigen starke Aktivitaet</span>
                </div>
              </div>
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

      {/* ─── Tabs ─── */}
      <div className="ob-tabs">
        <button
          className={`ob-tab-btn ${activeTab === 'zones' ? 'ob-tab-active' : ''}`}
          onClick={() => setActiveTab('zones')}
        >
          Zonen
        </button>
        <button
          className={`ob-tab-btn ${activeTab === 'backtest' ? 'ob-tab-active' : ''}`}
          onClick={() => setActiveTab('backtest')}
        >
          Backtest
        </button>
      </div>

      {/* ═══════════════ Tab: Zonen ═══════════════ */}
      {activeTab === 'zones' && (
        <>
          {/* Action Bar */}
          <div className="ob-action-bar">
            <button
              className="btn-ob-action"
              onClick={() => detectMutation.mutate()}
              disabled={detectMutation.isPending}
            >
              {detectMutation.isPending ? 'Analysiere...' : 'Detection starten'}
            </button>
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

          {/* KPI Cards */}
          {allZones.length > 0 && (
            <div className="ob-kpi-grid">
              <div className="ob-kpi-card">
                <h3>Total Zones</h3>
                <div className="ob-kpi-value">{allZones.length}</div>
                <div className="ob-kpi-sub">Erkannte Orderblocks</div>
              </div>
              <div className="ob-kpi-card ob-kpi-bordered-green">
                <h3>Unmitigated</h3>
                <div className="ob-kpi-value">{unmitCount}</div>
                <div className="ob-kpi-sub">Aktive Zonen</div>
              </div>
              <div className="ob-kpi-card ob-kpi-bordered-amber">
                <h3>High Conviction</h3>
                <div className="ob-kpi-value">{hcCount}</div>
                <div className="ob-kpi-sub">Z-Score &gt; Threshold</div>
              </div>
              <div className="ob-kpi-card ob-kpi-bordered-blue">
                <h3>Avg Conviction Score</h3>
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

          {/* Filters */}
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
              <button
                className="btn-ob-filter-reset"
                onClick={() => { setZoneStateFilter(''); setConvictionFilter(''); }}
              >
                Reset
              </button>
            </div>
          )}

          {/* State Distribution Chart */}
          {allZones.length > 0 && (
            <div className="ob-chart-section">
              <h3>Zone State Distribution</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={stateChartData} barSize={48}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                  <YAxis stroke="#64748b" fontSize={12} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                  />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {stateChartData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Zone Table */}
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
                    <tr key={zone.id}>
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
                      <td>{formatDate(zone.formed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : allZones.length === 0 && !detectMutation.isPending ? (
            <div className="ob-table-empty">
              Noch keine Zonen vorhanden. Starte eine Detection um Orderblocks zu erkennen.
            </div>
          ) : filteredZones.length === 0 ? (
            <div className="ob-table-empty">
              Keine Zonen fuer die aktuelle Filterauswahl.
            </div>
          ) : null}
        </>
      )}

      {/* ═══════════════ Tab: Backtest ═══════════════ */}
      {activeTab === 'backtest' && (
        <>
          {/* Action Bar */}
          <div className="ob-action-bar">
            <button
              className="btn-ob-action"
              onClick={() => backtestMutation.mutate()}
              disabled={backtestMutation.isPending}
            >
              {backtestMutation.isPending ? 'Backtesting...' : 'Backtest starten'}
            </button>
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

          {/* KPI Cards */}
          {metrics && (
            <div className="ob-kpi-grid">
              <div className="ob-kpi-card ob-kpi-bordered-green">
                <h3>Hit Rate</h3>
                <div className="ob-kpi-value ob-kpi-accent">
                  {formatNumber(metrics.hit_rate, 1)}%
                </div>
                <div className="ob-kpi-sub">
                  {metrics.hits} / {metrics.total_trades} Trades
                </div>
              </div>
              <div className="ob-kpi-card ob-kpi-bordered-amber">
                <h3>High-Conviction Hit Rate</h3>
                <div className="ob-kpi-value">
                  {metrics.high_conviction_hit_rate != null ? `${formatNumber(metrics.high_conviction_hit_rate, 1)}%` : 'N/A'}
                </div>
                <div className="ob-kpi-sub">Starke Signale</div>
              </div>
              <div className="ob-kpi-card">
                <h3>Avg Penetration</h3>
                <div className="ob-kpi-value">
                  {formatNumber(metrics.avg_penetration_depth_pct, 1)}%
                </div>
                <div className="ob-kpi-sub">Durchschnittliche Tiefe</div>
              </div>
              <div className="ob-kpi-card">
                <h3>Zones / Monat</h3>
                <div className="ob-kpi-value">
                  {formatNumber(metrics.zones_per_month, 1)}
                </div>
                <div className="ob-kpi-sub">Durchsatz</div>
              </div>
            </div>
          )}

          {/* Conviction Breakdown Chart */}
          {convChartData.length > 0 && (
            <div className="ob-chart-section">
              <h3>Conviction Breakdown</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={convChartData} barGap={2}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="level" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                  />
                  <Legend />
                  <Bar dataKey="Hits" fill="#16a34a" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Misses" fill="#dc2626" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Expired" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Trade Outcomes Table */}
          {sortedTrades.length > 0 && (
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
                    <tr key={idx}>
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

          {/* No backtest yet */}
          {!metrics && !backtestMutation.isPending && (
            <div className="ob-table-empty">
              Starte einen Backtest um Ergebnisse zu sehen.
            </div>
          )}

          {/* Historical Runs */}
          {runs.length > 0 && (
            <div className="ob-runs-section">
              <div className="ob-runs-header">
                <h3>Historische Backtest-Runs</h3>
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
                        {run.hit_rate != null ? `${formatNumber(run.hit_rate, 1)}%` : 'N/A'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="ob-disclaimer">
        Orderblock Detection basiert auf historischen Preisdaten und stellt keine Anlageberatung dar.
        Vergangene Ergebnisse garantieren keine zukuenftigen Resultate.
      </div>
    </div>
  );
};

export default Orderblock;
