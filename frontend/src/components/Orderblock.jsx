import { useState, useMemo, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import {
  getSettings, analyzeOrderblocks, getOrderblockZones, deleteOrderblockZones,
  getOrderblockBacktestRuns, getOrderblockCandles,
} from '../api/client';
import { formatNumber, formatDate } from '../utils/formatters';
import { useAppState } from '../contexts/AppStateContext';
import OrderblockChart from './OrderblockChart';
import OrderblockKPIs from './OrderblockKPIs';
import OrderblockFilters from './OrderblockFilters';
import OrderblockZoneTable from './OrderblockZoneTable';
import OrderblockTradeTable from './OrderblockTradeTable';
import './Orderblock.css';

// ─── Helpers ───

const zoneDistance = (zone, mp) => {
  const top = parseFloat(zone.zone_top) || 0;
  const bottom = parseFloat(zone.zone_bottom) || 0;
  if (mp >= bottom && mp <= top) return 0;
  return Math.min(Math.abs(mp - top), Math.abs(mp - bottom));
};

const Orderblock = () => {
  const { userId, marketPrice } = useAppState();
  const queryClient = useQueryClient();

  // ─── State ───
  const [selectedInterval, setSelectedInterval] = useState('4h');
  const [months, setMonths] = useState(6);
  const [zoneStateFilter, setZoneStateFilter] = useState('UNMITIGATED');
  const [convictionFilter, setConvictionFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [confluenceFilter, setConfluenceFilter] = useState('');
  const [zoneSortConfig, setZoneSortConfig] = useState({ key: 'price_distance', dir: 'asc' });
  const [tradeSortConfig, setTradeSortConfig] = useState({ key: null, dir: 'asc' });
  const [analyzeResult, setAnalyzeResult] = useState(null);
  const [message, setMessage] = useState(null);
  const [showTrades, setShowTrades] = useState(false);
  const [selectedZone, setSelectedZone] = useState(null);
  const [selectedTradeRow, setSelectedTradeRow] = useState(null);
  const msgTimerRef = useRef(null);

  const showMsg = (type, text) => {
    setMessage({ type, text });
    if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
    msgTimerRef.current = setTimeout(() => setMessage(null), 5000);
  };

  useEffect(() => {
    return () => { if (msgTimerRef.current) clearTimeout(msgTimerRef.current); };
  }, []);

  // ─── Queries ───

  const { data: settings } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
  });

  useEffect(() => {
    if (settings?.ob_interval) {
      setSelectedInterval(settings.ob_interval);
    }
  }, [settings?.ob_interval]);

  const { data: zonesData, isLoading: zonesLoading, isError: zonesError } = useQuery({
    queryKey: ['ob-zones', userId, selectedInterval],
    queryFn: () => getOrderblockZones(userId, { interval: selectedInterval }),
  });

  const { data: runsData, isError: runsError } = useQuery({
    queryKey: ['ob-backtest-runs', userId],
    queryFn: () => getOrderblockBacktestRuns(userId),
  });

  const { data: candleData, isLoading: candlesLoading, isError: candlesError } = useQuery({
    queryKey: ['ob-candles', userId, selectedZone?.id, selectedInterval],
    queryFn: () => getOrderblockCandles(userId, {
      interval: selectedInterval,
      zoneId: selectedZone.id,
    }),
    enabled: !!selectedZone,
    staleTime: 5 * 60 * 1000,
  });

  // ─── Mutations ───

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeOrderblocks(userId, { interval: selectedInterval, months }),
    onSuccess: (data) => {
      setAnalyzeResult(data);
      queryClient.invalidateQueries({ queryKey: ['ob-zones', userId] });
      queryClient.invalidateQueries({ queryKey: ['ob-backtest-runs', userId] });
      showMsg('success', `Analyse abgeschlossen: ${data.zones?.length || 0} Zonen, ${data.trades?.length || 0} Trades simuliert.`);
    },
    onError: (err) => showMsg('error', err.response?.data?.detail || err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteOrderblockZones(userId, { interval: selectedInterval }),
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
    if (confluenceFilter) z = z.filter(zone => zone.confluence_label === confluenceFilter);
    return z;
  }, [allZones, zoneStateFilter, convictionFilter, categoryFilter, confluenceFilter]);

  const sortedZones = useMemo(() => {
    if (!zoneSortConfig.key) return filteredZones;
    return [...filteredZones].sort((a, b) => {
      let av, bv;
      if (zoneSortConfig.key === 'price_distance') {
        const mp = marketPrice || 0;
        av = zoneDistance(a, mp);
        bv = zoneDistance(b, mp);
        const cmp = zoneSortConfig.dir === 'asc' ? av - bv : bv - av;
        if (cmp !== 0) return cmp;
        return (parseFloat(b.conviction_score) || 0) - (parseFloat(a.conviction_score) || 0);
      }
      av = a[zoneSortConfig.key]; bv = b[zoneSortConfig.key];
      if (zoneSortConfig.key === 'conviction_score' || zoneSortConfig.key === 'zone_top') {
        av = parseFloat(av) || 0; bv = parseFloat(bv) || 0;
      }
      if (av < bv) return zoneSortConfig.dir === 'asc' ? -1 : 1;
      if (av > bv) return zoneSortConfig.dir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filteredZones, zoneSortConfig, marketPrice]);

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
    queryKey: ['ob-candles-trade', userId, selectedTradeRow?.ob_id, selectedTradeRow?.entry_timestamp, selectedInterval],
    queryFn: () => getOrderblockCandles(userId, {
      interval: selectedInterval,
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
  }, [selectedInterval, zoneStateFilter, convictionFilter, categoryFilter, confluenceFilter]);

  // ─── Chart Data ───
  const metrics = analyzeResult?.metrics;

  const stateChartData = useMemo(() => [
    { name: 'Unmitigated', count: allZones.filter(z => z.state === 'UNMITIGATED').length, fill: '#16a34a' },
    { name: 'Mitigated', count: allZones.filter(z => z.state === 'MITIGATED').length, fill: '#94a3b8' },
    { name: 'Invalid', count: allZones.filter(z => z.state === 'INVALID').length, fill: '#dc2626' },
  ], [allZones]);

  const convChartData = useMemo(() => {
    const breakdown = metrics?.conviction_breakdown || [];
    return breakdown.map(cb => ({
      level: cb.level,
      Hits: cb.hits,
      Misses: cb.misses,
      Expired: cb.expired || 0,
    }));
  }, [metrics]);

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
            onClick={() => { if (window.confirm(`Alle ${allZones.length} Zonen (${selectedInterval}) löschen?`)) deleteMutation.mutate(); }}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Lösche...' : 'Alle Zonen löschen'}
          </button>
        )}
        <div className="ob-param-group">
          <label>Interval</label>
          <select value={selectedInterval} onChange={e => setSelectedInterval(e.target.value)}>
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

      {/* ─── KPI Cards ─── */}
      <OrderblockKPIs
        allZones={allZones}
        metrics={metrics}
        analyzeResult={analyzeResult}
      />

      {/* ─── Filters ─── */}
      {allZones.length > 0 && (
        <OrderblockFilters
          zoneStateFilter={zoneStateFilter} setZoneStateFilter={setZoneStateFilter}
          convictionFilter={convictionFilter} setConvictionFilter={setConvictionFilter}
          categoryFilter={categoryFilter} setCategoryFilter={setCategoryFilter}
          confluenceFilter={confluenceFilter} setConfluenceFilter={setConfluenceFilter}
        />
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
                    {stateChartData.map((entry) => (
                      <Cell key={entry.name} fill={entry.fill} />
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
      {zonesError ? (
        <div className="ob-error">Fehler beim Laden der Zonen. Bitte erneut versuchen.</div>
      ) : zonesLoading ? (
        <div className="ob-loading">Lade Zonen...</div>
      ) : (
        <OrderblockZoneTable
          sortedZones={sortedZones}
          selectedZone={selectedZone}
          onSelectZone={setSelectedZone}
          zoneSortConfig={zoneSortConfig}
          onSort={handleZoneSort}
          marketPrice={marketPrice}
        />
      )}

      {/* ─── Candlestick Chart (bei selektierter Zone) ─── */}
      {selectedZone && (candlesError ? (
        <div className="ob-error">Fehler beim Laden der Kerzen-Daten.</div>
      ) : (
        <OrderblockChart
          candles={candleData?.candles || []}
          zone={selectedZone}
          trade={selectedTrade}
          isLoading={candlesLoading}
        />
      ))}

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

      {/* ─── Trade Outcomes ─── */}
      <OrderblockTradeTable
        trades={trades}
        sortedTrades={sortedTrades}
        showTrades={showTrades}
        onToggleTrades={() => setShowTrades(v => !v)}
        selectedTradeRow={selectedTradeRow}
        onSelectTradeRow={setSelectedTradeRow}
        tradeSortConfig={tradeSortConfig}
        onSort={handleTradeSort}
        selectedTradeZone={selectedTradeZone}
        tradeCandleData={tradeCandleData}
        tradeCandlesLoading={tradeCandlesLoading}
      />

      {/* ─── Historical Runs ─── */}
      {runsError && <div className="ob-error">Fehler beim Laden der Analyse-Runs.</div>}
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
