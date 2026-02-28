/**
 * Chart.jsx - Dedicated full-page OHLCV candlestick chart
 *
 * Features:
 * - Full viewport chart (fills remaining space below sub-nav)
 * - Floating toolbar: interval buttons (15m, 1h, 4h, 1d, 1w) + lookback presets (1W, 1M, 3M, 6M)
 * - Volume histogram overlaid behind candles (semi-transparent, same pane)
 * - Orderblock zone overlays: paired dashed price lines (top/bottom) with conviction-based width
 * - Break-even line: blue dotted horizontal line with axis label
 * - Sell order lines: amber solid lines, clustered by 0.5% price proximity with count badge
 * - Trailing stop line: purple sparse-dotted line with frozen indicator
 * - Toggleable overlays via toolbar buttons (Zones, BE, Sells, Trail)
 * - Live polling (~30s) updates latest candle without full refetch
 * - Dark theme consistent with OrderblockChart (useChartTheme)
 *
 * Data source: existing /api/orderblock/{userId}/candles endpoint (start_time + end_time mode)
 */
import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
} from 'lightweight-charts';
import { useChartTheme, hexToRgb } from '../hooks/useChartTheme';
import { getOrderblockCandles, getOrderblockZones, getPortfolio, getOrdersForUser, getTrailingStops } from '../api/client';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import './Chart.css';

const TZ_OFFSET_SEC = new Date().getTimezoneOffset() * -60;

const INTERVALS = ['15m', '1h', '4h', '1d', '1w'];
const LOOKBACKS = ['1W', '1M', '3M', '6M'];

const POLLING_INTERVAL_MS = 30_000;

/**
 * Compute start/end timestamps from a lookback preset key.
 * Returns { startTime: ISO string, endTime: ISO string }.
 */
function computeTimeRange(lookback) {
  const now = new Date();
  const end = now.toISOString();
  let start;

  switch (lookback) {
    case '1W':
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      break;
    case '1M':
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      break;
    case '3M':
      start = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
      break;
    case '6M':
      start = new Date(now.getTime() - 180 * 24 * 60 * 60 * 1000);
      break;
    default:
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  }

  return { startTime: start.toISOString(), endTime: end };
}

/**
 * Compute the millisecond duration of one candle interval.
 */
function intervalMs(interval) {
  const map = {
    '15m': 15 * 60 * 1000,
    '1h': 60 * 60 * 1000,
    '4h': 4 * 60 * 60 * 1000,
    '1d': 24 * 60 * 60 * 1000,
    '1w': 7 * 24 * 60 * 60 * 1000,
  };
  return map[interval] || 60 * 60 * 1000;
}

/**
 * Cluster sell orders by price proximity.
 * Orders within `thresholdPct` (0.5%) of the running cluster average are grouped.
 * Returns array of { avgPrice, count, orders }.
 */
function clusterOrders(orders, thresholdPct = 0.005) {
  if (!orders?.length) return [];

  const sorted = [...orders]
    .map((o) => ({ ...o, priceNum: parseFloat(o.price) }))
    .filter((o) => o.priceNum > 0 && isFinite(o.priceNum))
    .sort((a, b) => a.priceNum - b.priceNum);

  if (!sorted.length) return [];

  const clusters = [];
  let current = { sum: sorted[0].priceNum, count: 1, orders: [sorted[0]] };

  for (let i = 1; i < sorted.length; i++) {
    const avg = current.sum / current.count;
    if (Math.abs(sorted[i].priceNum - avg) / avg <= thresholdPct) {
      current.sum += sorted[i].priceNum;
      current.count += 1;
      current.orders.push(sorted[i]);
    } else {
      clusters.push({
        avgPrice: current.sum / current.count,
        count: current.count,
        orders: current.orders,
      });
      current = { sum: sorted[i].priceNum, count: 1, orders: [sorted[i]] };
    }
  }
  clusters.push({
    avgPrice: current.sum / current.count,
    count: current.count,
    orders: current.orders,
  });

  return clusters;
}

const Chart = () => {
  const { symbol } = useSymbol();
  const { userId } = useUser();
  const theme = useChartTheme();

  const [selectedInterval, setSelectedInterval] = useState('1h');
  const [lookback, setLookback] = useState('1M');
  const [showZones, setShowZones] = useState(true);
  const [showBreakEven, setShowBreakEven] = useState(true);
  const [showSellOrders, setShowSellOrders] = useState(true);
  const [showTrailingStop, setShowTrailingStop] = useState(true);

  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const resizeObserverRef = useRef(null);
  const pollingRef = useRef(null);
  const overlayLinesRef = useRef([]);

  // Compute time range from lookback
  const timeRange = useMemo(() => computeTimeRange(lookback), [lookback]);

  // Fetch candles via TanStack Query
  const {
    data: candleData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['chart-candles', symbol, selectedInterval, lookback],
    queryFn: () =>
      getOrderblockCandles(userId, {
        symbol,
        interval: selectedInterval,
        startTime: timeRange.startTime,
        endTime: timeRange.endTime,
        contextCandles: 20,
      }),
    staleTime: 20_000,
    refetchOnWindowFocus: false,
  });

  const candles = candleData?.candles || [];

  // Fetch orderblock zones for current symbol/interval (exclude INVALID client-side)
  const { data: zonesData } = useQuery({
    queryKey: ['chart-zones', symbol, selectedInterval],
    queryFn: () =>
      getOrderblockZones(userId, {
        symbol,
        interval: selectedInterval,
      }),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  // Fetch portfolio break-even (use latest candle close as market_price)
  const latestClose = candles.length > 0 ? candles[candles.length - 1].close : null;

  const { data: portfolioData } = useQuery({
    queryKey: ['chart-portfolio', symbol, latestClose],
    queryFn: () => getPortfolio(userId, latestClose, symbol),
    enabled: !!latestClose,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  // Fetch open sell orders for current symbol
  const { data: ordersData } = useQuery({
    queryKey: ['chart-orders', symbol],
    queryFn: () => getOrdersForUser(userId, 'OPEN', symbol),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchInterval: 60_000,
  });

  // Fetch trailing stops
  const { data: trailingData } = useQuery({
    queryKey: ['chart-trailing-stops'],
    queryFn: () => getTrailingStops(userId),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchInterval: 30_000,
  });

  // ---- Chart creation (recreate on theme change) ----
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Compute height: fill remaining viewport below the container's top
    const rect = chartContainerRef.current.getBoundingClientRect();
    const height = window.innerHeight - rect.top;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: theme.bgPage },
        textColor: theme.textSecondary,
        fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
      },
      grid: {
        vertLines: { color: theme.borderLight },
        horzLines: { color: theme.borderLight },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: theme.border },
      timeScale: {
        borderColor: theme.border,
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartContainerRef.current.clientWidth,
      height,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: theme.profit,
      downColor: theme.loss,
      borderUpColor: theme.profit,
      borderDownColor: theme.loss,
      wickUpColor: theme.profit,
      wickDownColor: theme.loss,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: theme.textMuted,
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // ResizeObserver for width + window resize for height
    const handleResize = () => {
      if (!chartContainerRef.current || !chartRef.current) return;
      const newRect = chartContainerRef.current.getBoundingClientRect();
      const newHeight = window.innerHeight - newRect.top;
      chartRef.current.applyOptions({
        width: chartContainerRef.current.clientWidth,
        height: newHeight,
      });
    };

    const ro = new ResizeObserver(() => handleResize());
    ro.observe(chartContainerRef.current);
    resizeObserverRef.current = ro;

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      ro.disconnect();
      resizeObserverRef.current = null;
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [theme]);

  // ---- Data update ----
  useEffect(() => {
    if (!candles.length || !candleSeriesRef.current) return;

    const adjusted = candles.map((c) => ({ ...c, time: c.time + TZ_OFFSET_SEC }));

    candleSeriesRef.current.setData(adjusted);
    volumeSeriesRef.current.setData(
      adjusted.map((c) => ({
        time: c.time,
        value: c.volume,
        color:
          c.close >= c.open
            ? `rgba(${hexToRgb(theme.profit)}, 0.3)`
            : `rgba(${hexToRgb(theme.loss)}, 0.3)`,
      }))
    );

    chartRef.current?.timeScale().fitContent();
  }, [candles, theme]);

  // ---- Overlay rendering (zones + break-even) ----
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;

    // Clean up previous overlay lines
    overlayLinesRef.current.forEach((pl) => {
      try { series.removePriceLine(pl); } catch { /* already removed */ }
    });
    overlayLinesRef.current = [];

    // --- Orderblock Zones ---
    if (showZones && zonesData?.zones) {
      const visibleZones = zonesData.zones.filter(
        (z) => z.state === 'UNMITIGATED' || z.state === 'MITIGATED'
      );

      for (const zone of visibleZones) {
        const isBullish = zone.direction === 'BULLISH';
        const baseColor = isBullish ? theme.profit : theme.loss;
        const isMitigated = zone.state === 'MITIGATED';

        // Conviction-based line width: LOW=1, STANDARD=1, HIGH=2, INSTITUTIONAL=3
        const convictionWidth = zone.conviction === 'INSTITUTIONAL' ? 3
          : zone.conviction === 'HIGH' ? 2 : 1;

        // Opacity: UNMITIGATED full, MITIGATED dimmed
        const alpha = isMitigated ? 0.35 : 0.7;
        const lineColor = `rgba(${hexToRgb(baseColor)}, ${alpha})`;

        // Zone top line
        overlayLinesRef.current.push(
          series.createPriceLine({
            price: parseFloat(zone.zone_top),
            color: lineColor,
            lineWidth: convictionWidth,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: false,
            title: '',
          })
        );

        // Zone bottom line
        overlayLinesRef.current.push(
          series.createPriceLine({
            price: parseFloat(zone.zone_bottom),
            color: lineColor,
            lineWidth: convictionWidth,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: false,
            title: '',
          })
        );
      }
    }

    // --- Break-Even Line ---
    if (showBreakEven && portfolioData?.break_even) {
      const bePrice = parseFloat(portfolioData.break_even);
      if (bePrice > 0 && isFinite(bePrice)) {
        overlayLinesRef.current.push(
          series.createPriceLine({
            price: bePrice,
            color: theme.accentBlue,
            lineWidth: 2,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: true,
            title: 'Break-Even',
          })
        );
      }
    }

    // --- Sell Order Lines (clustered) ---
    if (showSellOrders && ordersData?.orders) {
      const clusters = clusterOrders(ordersData.orders);
      for (const cluster of clusters) {
        const title = cluster.count > 1
          ? `${cluster.count} Orders`
          : 'Sell';
        overlayLinesRef.current.push(
          series.createPriceLine({
            price: cluster.avgPrice,
            color: theme.accentAmber,
            lineWidth: cluster.count > 1 ? 2 : 1,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title,
          })
        );
      }
    }

    // --- Trailing Stop Level ---
    if (showTrailingStop && trailingData?.stops) {
      const symbolStop = trailingData.stops[symbol];
      if (symbolStop?.stop_level) {
        const stopPrice = parseFloat(symbolStop.stop_level);
        if (stopPrice > 0 && isFinite(stopPrice)) {
          const isFrozen = symbolStop.frozen;
          overlayLinesRef.current.push(
            series.createPriceLine({
              price: stopPrice,
              color: theme.chart1,
              lineWidth: 2,
              lineStyle: LineStyle.SparseDotted,
              axisLabelVisible: true,
              title: isFrozen ? 'Trail Stop (frozen)' : 'Trail Stop',
            })
          );
        }
      }
    }

    return () => {
      overlayLinesRef.current.forEach((pl) => {
        try { series.removePriceLine(pl); } catch { /* already removed */ }
      });
      overlayLinesRef.current = [];
    };
  }, [showZones, showBreakEven, showSellOrders, showTrailingStop, zonesData, portfolioData, ordersData, trailingData, candles, theme, symbol]);

  // ---- Live polling (30s interval) ----
  const fetchLatestCandle = useCallback(async () => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    try {
      const now = new Date();
      const twoIntervalsAgo = new Date(now.getTime() - 2 * intervalMs(selectedInterval));
      const result = await getOrderblockCandles(userId, {
        symbol,
        interval: selectedInterval,
        startTime: twoIntervalsAgo.toISOString(),
        endTime: now.toISOString(),
        contextCandles: 20,
      });

      const freshCandles = result?.candles;
      if (!freshCandles?.length) return;

      // Update the latest candles (lightweight-charts update() merges or appends)
      for (const c of freshCandles) {
        const adjusted = { ...c, time: c.time + TZ_OFFSET_SEC };
        candleSeriesRef.current.update(adjusted);
        volumeSeriesRef.current.update({
          time: adjusted.time,
          value: adjusted.volume,
          color:
            adjusted.close >= adjusted.open
              ? `rgba(${hexToRgb(theme.profit)}, 0.3)`
              : `rgba(${hexToRgb(theme.loss)}, 0.3)`,
        });
      }
    } catch (err) {
      // Graceful: polling failure is non-critical, just log
      console.warn('Chart polling update failed:', err);
    }
  }, [userId, symbol, selectedInterval, theme]);

  useEffect(() => {
    // Only poll if we have initial data
    if (!candles.length) return;

    pollingRef.current = setInterval(fetchLatestCandle, POLLING_INTERVAL_MS);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [fetchLatestCandle, candles.length]);

  // ---- Loading state ----
  if (isLoading && !candles.length) {
    return (
      <div className="chart-page">
        <div className="chart-loading">Lade Chart-Daten...</div>
      </div>
    );
  }

  // ---- Error state ----
  if (isError && !candles.length) {
    return (
      <div className="chart-page">
        <div className="chart-error">
          <p>Fehler beim Laden der Chart-Daten.</p>
          <p className="chart-error-detail">{error?.message || 'Unbekannter Fehler'}</p>
          <button className="chart-retry-btn" onClick={() => refetch()}>
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="chart-page">
      {/* Floating Toolbar */}
      <div className="chart-toolbar">
        <div className="chart-toolbar-group">
          {INTERVALS.map((iv) => (
            <button
              key={iv}
              className={`chart-toolbar-btn ${selectedInterval === iv ? 'active' : ''}`}
              onClick={() => setSelectedInterval(iv)}
            >
              {iv}
            </button>
          ))}
        </div>
        <div className="chart-toolbar-divider" />
        <div className="chart-toolbar-group">
          {LOOKBACKS.map((lb) => (
            <button
              key={lb}
              className={`chart-toolbar-btn ${lookback === lb ? 'active' : ''}`}
              onClick={() => setLookback(lb)}
            >
              {lb}
            </button>
          ))}
        </div>
        <div className="chart-toolbar-divider" />
        <div className="chart-toolbar-group">
          <button
            className={`chart-toolbar-btn chart-toggle-btn ${showZones ? 'toggle-active' : ''}`}
            onClick={() => setShowZones((v) => !v)}
            title="Orderblock Zones"
          >
            Zones
          </button>
          <button
            className={`chart-toolbar-btn chart-toggle-btn ${showBreakEven ? 'toggle-active' : ''}`}
            onClick={() => setShowBreakEven((v) => !v)}
            title="Break-Even Preis"
          >
            BE
          </button>
          <button
            className={`chart-toolbar-btn chart-toggle-btn ${showSellOrders ? 'toggle-active' : ''}`}
            onClick={() => setShowSellOrders((v) => !v)}
            title="Offene Sell Orders"
          >
            Sells
          </button>
          <button
            className={`chart-toolbar-btn chart-toggle-btn ${showTrailingStop ? 'toggle-active' : ''}`}
            onClick={() => setShowTrailingStop((v) => !v)}
            title="Trailing Stop Level"
          >
            Trail
          </button>
        </div>
      </div>

      {/* Chart container */}
      <div ref={chartContainerRef} className="chart-container" />
    </div>
  );
};

export default Chart;
