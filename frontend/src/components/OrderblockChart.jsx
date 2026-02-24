import { useRef, useEffect } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createSeriesMarkers,
} from 'lightweight-charts';
import { formatEUR, formatDate, formatTime } from '../utils/formatters';
import { useChartTheme, hexToRgb } from '../hooks/useChartTheme';

const TZ_OFFSET_SEC = new Date().getTimezoneOffset() * -60;

const OrderblockChart = ({ candles, zone, trade, isLoading }) => {
  const theme = useChartTheme();
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const markersRef = useRef(null);
  const priceLinesRef = useRef([]);

  // ─── Chart erstellen (einmalig) ───
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: theme.bgCard },
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
      height: 420,
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

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(chartContainerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [theme]);

  // ─── Daten updaten ───
  useEffect(() => {
    if (!candles?.length || !candleSeriesRef.current) return;

    // lightweight-charts zeigt UTC — Offset addieren fuer lokale Zeitanzeige
    const adjusted = candles.map(c => ({ ...c, time: c.time + TZ_OFFSET_SEC }));

    candleSeriesRef.current.setData(adjusted);
    volumeSeriesRef.current.setData(
      adjusted.map(c => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open
          ? `rgba(${hexToRgb(theme.profit)}, 0.3)`
          : `rgba(${hexToRgb(theme.loss)}, 0.3)`,
      }))
    );

    chartRef.current.timeScale().fitContent();
  }, [candles, theme]);

  // ─── Zone-Overlay + Trade-Levels ───
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series || !zone || !candles?.length) return;

    // Vorherige PriceLines entfernen
    priceLinesRef.current.forEach(pl => {
      try { series.removePriceLine(pl); } catch (_) { /* ignore */ }
    });
    priceLinesRef.current = [];

    // Vorherige Markers entfernen
    if (markersRef.current) {
      series.detachPrimitive(markersRef.current);
      markersRef.current = null;
    }

    const isBullish = zone.direction === 'BULLISH';
    const zoneBorder = isBullish ? theme.profit : theme.loss;

    // Zone Top/Bottom PriceLines
    priceLinesRef.current.push(
      series.createPriceLine({
        price: parseFloat(zone.zone_top),
        color: zoneBorder,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: isBullish ? 'Zone Top ↑' : 'Zone Top ↓',
      }),
      series.createPriceLine({
        price: parseFloat(zone.zone_bottom),
        color: zoneBorder,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'Zone Bottom',
      }),
      // Equilibrium
      series.createPriceLine({
        price: parseFloat(zone.equilibrium),
        color: theme.accentOrderblock,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: false,
        title: 'EQ',
      })
    );

    // Liquidity Sweep Level (falls vorhanden)
    if (zone.liquidity_sweep_level) {
      priceLinesRef.current.push(
        series.createPriceLine({
          price: parseFloat(zone.liquidity_sweep_level),
          color: theme.accentAmber,
          lineWidth: 1,
          lineStyle: LineStyle.SparseDotted,
          axisLabelVisible: true,
          title: 'Sweep',
        })
      );
    }

    // ─── Markers: OB-definierende Kerzen + Trade Entry/Exit ───
    const markers = [];

    // Formation-Kerze (OB-Basis)
    if (zone.formed_at) {
      markers.push({
        time: Math.floor(new Date(zone.formed_at).getTime() / 1000) + TZ_OFFSET_SEC,
        position: isBullish ? 'belowBar' : 'aboveBar',
        color: theme.accentOrderblock,
        shape: 'square',
        text: 'OB',
      });
    }

    // Confirmation-Kerze (Break of Structure)
    if (zone.confirmed_at) {
      markers.push({
        time: Math.floor(new Date(zone.confirmed_at).getTime() / 1000) + TZ_OFFSET_SEC,
        position: isBullish ? 'aboveBar' : 'belowBar',
        color: theme.accentOrderblock,
        shape: 'circle',
        text: 'BOS',
      });
    }

    // Trade-Levels (falls vorhanden)
    if (trade) {
      if (trade.entry_edge) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: parseFloat(trade.entry_edge),
            color: theme.accentBlue,
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: 'Entry',
          })
        );
      }
      if (trade.stop_edge) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: parseFloat(trade.stop_edge),
            color: theme.loss,
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: 'Stop',
          })
        );
      }
      if (trade.target) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: parseFloat(trade.target),
            color: theme.profit,
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: 'Target',
          })
        );
      }

      // Trade Entry/Exit Markers
      if (trade.entry_timestamp) {
        markers.push({
          time: Math.floor(new Date(trade.entry_timestamp).getTime() / 1000) + TZ_OFFSET_SEC,
          position: isBullish ? 'belowBar' : 'aboveBar',
          color: theme.accentBlue,
          shape: isBullish ? 'arrowUp' : 'arrowDown',
          text: 'Entry',
        });
      }
      if (trade.exit_timestamp) {
        const isHit = trade.outcome === 'HIT';
        markers.push({
          time: Math.floor(new Date(trade.exit_timestamp).getTime() / 1000) + TZ_OFFSET_SEC,
          position: isBullish ? 'aboveBar' : 'belowBar',
          color: isHit ? theme.profit : theme.loss,
          shape: isBullish ? 'arrowDown' : 'arrowUp',
          text: trade.outcome,
        });
      }
    }

    // Alle Markers setzen (chronologisch sortiert)
    if (markers.length) {
      markers.sort((a, b) => a.time - b.time);
      markersRef.current = createSeriesMarkers(series, markers);
    }

    return () => {
      priceLinesRef.current.forEach(pl => {
        try { series.removePriceLine(pl); } catch (_) { /* ignore */ }
      });
      priceLinesRef.current = [];
      if (markersRef.current) {
        series.detachPrimitive(markersRef.current);
        markersRef.current = null;
      }
    };
  }, [zone, trade, candles, theme]);

  if (isLoading) {
    return <div className="ob-chart-loading">Lade Kerzen...</div>;
  }

  if (!candles?.length) {
    return <div className="ob-chart-loading">Keine Kerzen-Daten verfuegbar.</div>;
  }

  return (
    <div className="ob-candlestick-section">
      <div className="ob-candlestick-header">
        <h3>
          Preisumfeld — {zone?.direction === 'BULLISH' ? '↑ Bullish' : '↓ Bearish'} Zone
        </h3>
        <div className="ob-candlestick-legend">
          <span className="ob-legend-item ob-legend-ob">OB</span>
          <span className="ob-legend-item ob-legend-bos">BOS</span>
          <span className="ob-legend-item ob-legend-zone">Zone</span>
          <span className="ob-legend-item ob-legend-eq">EQ</span>
          {trade && <span className="ob-legend-item ob-legend-entry">Entry</span>}
          {trade && <span className="ob-legend-item ob-legend-stop">Stop</span>}
          {trade && <span className="ob-legend-item ob-legend-target">Target</span>}
        </div>
      </div>
      <div ref={chartContainerRef} className="ob-candlestick-container" />
      {zone && (
        <div className="ob-candlestick-info">
          <span>Zone: {formatEUR(zone.zone_bottom)} — {formatEUR(zone.zone_top)}</span>
          <span>Formed: {formatDate(zone.formed_at)} {formatTime(zone.formed_at)}</span>
          {trade && (
            <span>
              Outcome:{' '}
              <span className={`ob-badge outcome-${trade.outcome.toLowerCase()}`}>
                {trade.outcome}
              </span>
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default OrderblockChart;
