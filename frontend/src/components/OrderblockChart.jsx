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

const OrderblockChart = ({ candles, zone, trade, isLoading }) => {
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
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#64748b',
        fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
      },
      grid: {
        vertLines: { color: '#f1f5f9' },
        horzLines: { color: '#f1f5f9' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#e2e8f0' },
      timeScale: {
        borderColor: '#e2e8f0',
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartContainerRef.current.clientWidth,
      height: 420,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#16a34a',
      downColor: '#dc2626',
      borderUpColor: '#16a34a',
      borderDownColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#94a3b8',
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
  }, []);

  // ─── Daten updaten ───
  useEffect(() => {
    if (!candles?.length || !candleSeriesRef.current) return;

    // lightweight-charts zeigt UTC — Offset addieren fuer lokale Zeitanzeige
    const tzOffsetSec = new Date().getTimezoneOffset() * -60;
    const adjusted = candles.map(c => ({ ...c, time: c.time + tzOffsetSec }));

    candleSeriesRef.current.setData(adjusted);
    volumeSeriesRef.current.setData(
      adjusted.map(c => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(22,163,74,0.25)' : 'rgba(220,38,38,0.25)',
      }))
    );

    chartRef.current.timeScale().fitContent();
  }, [candles]);

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
    const zoneBorder = isBullish ? '#16a34a' : '#dc2626';

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
        color: '#d97706',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: false,
        title: 'EQ',
      })
    );

    // ─── Markers: OB-definierende Kerzen + Trade Entry/Exit ───
    const tzOffsetSec = new Date().getTimezoneOffset() * -60;
    const markers = [];

    // Formation-Kerze (OB-Basis)
    if (zone.formed_at) {
      markers.push({
        time: Math.floor(new Date(zone.formed_at).getTime() / 1000) + tzOffsetSec,
        position: isBullish ? 'belowBar' : 'aboveBar',
        color: '#d97706',
        shape: 'square',
        text: 'OB',
      });
    }

    // Confirmation-Kerze (Break of Structure)
    if (zone.confirmed_at) {
      markers.push({
        time: Math.floor(new Date(zone.confirmed_at).getTime() / 1000) + tzOffsetSec,
        position: isBullish ? 'aboveBar' : 'belowBar',
        color: '#d97706',
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
            color: '#3b82f6',
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
            color: '#dc2626',
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
            color: '#16a34a',
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
          time: Math.floor(new Date(trade.entry_timestamp).getTime() / 1000) + tzOffsetSec,
          position: isBullish ? 'belowBar' : 'aboveBar',
          color: '#3b82f6',
          shape: isBullish ? 'arrowUp' : 'arrowDown',
          text: 'Entry',
        });
      }
      if (trade.exit_timestamp) {
        const isHit = trade.outcome === 'HIT';
        markers.push({
          time: Math.floor(new Date(trade.exit_timestamp).getTime() / 1000) + tzOffsetSec,
          position: isBullish ? 'aboveBar' : 'belowBar',
          color: isHit ? '#16a34a' : '#dc2626',
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
  }, [zone, trade, candles]);

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
