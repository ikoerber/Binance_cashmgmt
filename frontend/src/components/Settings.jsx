import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSettings, updateSettings } from '../api/client';
import { useUser } from '../contexts/UserContext';
import useNotification from '../hooks/useNotification';
import './Settings.css';

const ALPHA_DEFAULTS = {
  alpha_score_interval: '15m',
  alpha_score_weight_zscore: '40',
  alpha_score_weight_leadlag: '30',
  alpha_score_weight_imbalance: '20',
  alpha_score_weight_funding: '10',
  alpha_score_threshold: '3.0',
  alpha_score_zscore_window: '60',
  alpha_score_leadlag_window: '30',
  alpha_score_hurst_lookback: '100',
  alpha_score_hurst_trending: '0.55',
  alpha_score_hurst_reverting: '0.45',
  alpha_score_atr_mult_btc: '2.0',
  alpha_score_atr_mult_xrp: '3.0',
  alpha_score_stop_resume_n: '5',
};

const Settings = () => {
  const { userId } = useUser();
  const queryClient = useQueryClient();
  const { message, showMessage, dismissMessage } = useNotification();
  const [maxOrderValueEur, setMaxOrderValueEur] = useState('');
  const [macroSignalInterval, setMacroSignalInterval] = useState('15');
  const [sellAllocationStrategy, setSellAllocationStrategy] = useState('FIFO');
  const [obInterval, setObInterval] = useState('4h');
  const [obAtrMultiplier, setObAtrMultiplier] = useState('2.0');
  const [obTargetRr, setObTargetRr] = useState('2.0');
  const [obImpulseWindow, setObImpulseWindow] = useState('5');
  const [reconToleranceBase, setReconToleranceBase] = useState('0.0001');
  const [reconToleranceQuote, setReconToleranceQuote] = useState('1.00');

  // Alpha Score Settings
  const [alphaInterval, setAlphaInterval] = useState(ALPHA_DEFAULTS.alpha_score_interval);
  const [alphaWeightZscore, setAlphaWeightZscore] = useState(ALPHA_DEFAULTS.alpha_score_weight_zscore);
  const [alphaWeightLeadlag, setAlphaWeightLeadlag] = useState(ALPHA_DEFAULTS.alpha_score_weight_leadlag);
  const [alphaWeightImbalance, setAlphaWeightImbalance] = useState(ALPHA_DEFAULTS.alpha_score_weight_imbalance);
  const [alphaWeightFunding, setAlphaWeightFunding] = useState(ALPHA_DEFAULTS.alpha_score_weight_funding);
  const [alphaThreshold, setAlphaThreshold] = useState(ALPHA_DEFAULTS.alpha_score_threshold);
  const [alphaZscoreWindow, setAlphaZscoreWindow] = useState(ALPHA_DEFAULTS.alpha_score_zscore_window);
  const [alphaLeadlagWindow, setAlphaLeadlagWindow] = useState(ALPHA_DEFAULTS.alpha_score_leadlag_window);
  const [alphaHurstLookback, setAlphaHurstLookback] = useState(ALPHA_DEFAULTS.alpha_score_hurst_lookback);
  const [alphaHurstTrending, setAlphaHurstTrending] = useState(ALPHA_DEFAULTS.alpha_score_hurst_trending);
  const [alphaHurstReverting, setAlphaHurstReverting] = useState(ALPHA_DEFAULTS.alpha_score_hurst_reverting);
  const [alphaAtrMultBtc, setAlphaAtrMultBtc] = useState(ALPHA_DEFAULTS.alpha_score_atr_mult_btc);
  const [alphaAtrMultXrp, setAlphaAtrMultXrp] = useState(ALPHA_DEFAULTS.alpha_score_atr_mult_xrp);
  const [alphaStopResumeN, setAlphaStopResumeN] = useState(ALPHA_DEFAULTS.alpha_score_stop_resume_n);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings', userId],
    queryFn: () => getSettings(userId),
  });

  useEffect(() => {
    if (settings) {
      setMaxOrderValueEur(settings.max_order_value_eur);
      setMacroSignalInterval(settings.macro_signal_interval || '15');
      setSellAllocationStrategy(settings.sell_allocation_strategy || 'FIFO');
      setObInterval(settings.ob_interval || '4h');
      setObAtrMultiplier(settings.ob_atr_multiplier ?? '2.0');
      setObTargetRr(settings.ob_target_rr ?? '2.0');
      setObImpulseWindow(settings.ob_impulse_window ?? '5');
      setReconToleranceBase(settings.recon_tolerance_base ?? '0.0001');
      setReconToleranceQuote(settings.recon_tolerance_quote ?? '1.00');
      // Alpha Score
      setAlphaInterval(settings.alpha_score_interval || ALPHA_DEFAULTS.alpha_score_interval);
      setAlphaWeightZscore(settings.alpha_score_weight_zscore ?? ALPHA_DEFAULTS.alpha_score_weight_zscore);
      setAlphaWeightLeadlag(settings.alpha_score_weight_leadlag ?? ALPHA_DEFAULTS.alpha_score_weight_leadlag);
      setAlphaWeightImbalance(settings.alpha_score_weight_imbalance ?? ALPHA_DEFAULTS.alpha_score_weight_imbalance);
      setAlphaWeightFunding(settings.alpha_score_weight_funding ?? ALPHA_DEFAULTS.alpha_score_weight_funding);
      setAlphaThreshold(settings.alpha_score_threshold ?? ALPHA_DEFAULTS.alpha_score_threshold);
      setAlphaZscoreWindow(String(settings.alpha_score_zscore_window ?? ALPHA_DEFAULTS.alpha_score_zscore_window));
      setAlphaLeadlagWindow(String(settings.alpha_score_leadlag_window ?? ALPHA_DEFAULTS.alpha_score_leadlag_window));
      setAlphaHurstLookback(String(settings.alpha_score_hurst_lookback ?? ALPHA_DEFAULTS.alpha_score_hurst_lookback));
      setAlphaHurstTrending(settings.alpha_score_hurst_trending ?? ALPHA_DEFAULTS.alpha_score_hurst_trending);
      setAlphaHurstReverting(settings.alpha_score_hurst_reverting ?? ALPHA_DEFAULTS.alpha_score_hurst_reverting);
      setAlphaAtrMultBtc(settings.alpha_score_atr_mult_btc ?? ALPHA_DEFAULTS.alpha_score_atr_mult_btc);
      setAlphaAtrMultXrp(settings.alpha_score_atr_mult_xrp ?? ALPHA_DEFAULTS.alpha_score_atr_mult_xrp);
      setAlphaStopResumeN(String(settings.alpha_score_stop_resume_n ?? ALPHA_DEFAULTS.alpha_score_stop_resume_n));
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: (values) => updateSettings(userId, values),
    onSuccess: () => {
      showMessage('success', 'Settings gespeichert.');
      queryClient.invalidateQueries({ queryKey: ['settings', userId] });
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  // Compute normalized weight display percentages
  const weightSum = (parseFloat(alphaWeightZscore) || 0) +
    (parseFloat(alphaWeightLeadlag) || 0) +
    (parseFloat(alphaWeightImbalance) || 0) +
    (parseFloat(alphaWeightFunding) || 0);
  const normalizeWeight = (val) => {
    const v = parseFloat(val) || 0;
    if (weightSum <= 0) return '0';
    return ((v / weightSum) * 100).toFixed(1);
  };

  const handleResetAlphaDefaults = () => {
    setAlphaInterval(ALPHA_DEFAULTS.alpha_score_interval);
    setAlphaWeightZscore(ALPHA_DEFAULTS.alpha_score_weight_zscore);
    setAlphaWeightLeadlag(ALPHA_DEFAULTS.alpha_score_weight_leadlag);
    setAlphaWeightImbalance(ALPHA_DEFAULTS.alpha_score_weight_imbalance);
    setAlphaWeightFunding(ALPHA_DEFAULTS.alpha_score_weight_funding);
    setAlphaThreshold(ALPHA_DEFAULTS.alpha_score_threshold);
    setAlphaZscoreWindow(ALPHA_DEFAULTS.alpha_score_zscore_window);
    setAlphaLeadlagWindow(ALPHA_DEFAULTS.alpha_score_leadlag_window);
    setAlphaHurstLookback(ALPHA_DEFAULTS.alpha_score_hurst_lookback);
    setAlphaHurstTrending(ALPHA_DEFAULTS.alpha_score_hurst_trending);
    setAlphaHurstReverting(ALPHA_DEFAULTS.alpha_score_hurst_reverting);
    setAlphaAtrMultBtc(ALPHA_DEFAULTS.alpha_score_atr_mult_btc);
    setAlphaAtrMultXrp(ALPHA_DEFAULTS.alpha_score_atr_mult_xrp);
    setAlphaStopResumeN(ALPHA_DEFAULTS.alpha_score_stop_resume_n);
    showMessage('success', 'Alpha Score Defaults wiederhergestellt. Klicke "Speichern" zum Uebernehmen.');
  };

  const handleSave = () => {
    const value = parseFloat(maxOrderValueEur);
    if (isNaN(value) || value <= 0) {
      showMessage('error', 'Bitte einen gueltigen Wert > 0 eingeben.');
      return;
    }
    const atrMult = parseFloat(obAtrMultiplier);
    if (isNaN(atrMult) || atrMult < 0.5 || atrMult > 10) {
      showMessage('error', 'ATR Multiplikator muss zwischen 0.5 und 10.0 liegen.');
      return;
    }
    const targetRr = parseFloat(obTargetRr);
    if (isNaN(targetRr) || targetRr < 0.5 || targetRr > 10) {
      showMessage('error', 'Target R:R muss zwischen 0.5 und 10.0 liegen.');
      return;
    }
    const impulseW = parseInt(obImpulseWindow, 10);
    if (isNaN(impulseW) || impulseW < 2 || impulseW > 20) {
      showMessage('error', 'Impulse Window muss zwischen 2 und 20 liegen.');
      return;
    }
    const toleranceBase = parseFloat(reconToleranceBase);
    if (isNaN(toleranceBase) || toleranceBase < 0) {
      showMessage('error', 'Base-Toleranz muss eine Zahl >= 0 sein.');
      return;
    }
    const toleranceQuote = parseFloat(reconToleranceQuote);
    if (isNaN(toleranceQuote) || toleranceQuote < 0) {
      showMessage('error', 'Quote-Toleranz muss eine Zahl >= 0 sein.');
      return;
    }
    // Alpha Score validation
    const aThreshold = parseFloat(alphaThreshold);
    if (isNaN(aThreshold) || aThreshold < 0.1 || aThreshold > 5.0) {
      showMessage('error', 'Alpha Score Schwelle muss zwischen 0.1 und 5.0 liegen.');
      return;
    }
    const aZscoreW = parseInt(alphaZscoreWindow, 10);
    if (isNaN(aZscoreW) || aZscoreW < 10 || aZscoreW > 500) {
      showMessage('error', 'Z-Score Window muss zwischen 10 und 500 liegen.');
      return;
    }
    const aLeadlagW = parseInt(alphaLeadlagWindow, 10);
    if (isNaN(aLeadlagW) || aLeadlagW < 10 || aLeadlagW > 500) {
      showMessage('error', 'Lead-Lag Window muss zwischen 10 und 500 liegen.');
      return;
    }
    const aHurstLB = parseInt(alphaHurstLookback, 10);
    if (isNaN(aHurstLB) || aHurstLB < 10 || aHurstLB > 500) {
      showMessage('error', 'Hurst Lookback muss zwischen 10 und 500 liegen.');
      return;
    }
    const aResumeN = parseInt(alphaStopResumeN, 10);
    if (isNaN(aResumeN) || aResumeN < 1 || aResumeN > 50) {
      showMessage('error', 'Stop Resume N muss zwischen 1 und 50 liegen.');
      return;
    }
    saveMutation.mutate({
      max_order_value_eur: String(value),
      macro_signal_interval: macroSignalInterval,
      sell_allocation_strategy: sellAllocationStrategy,
      ob_interval: obInterval,
      ob_atr_multiplier: String(atrMult),
      ob_target_rr: String(targetRr),
      ob_impulse_window: impulseW,
      recon_tolerance_base: reconToleranceBase,
      recon_tolerance_quote: reconToleranceQuote,
      // Alpha Score
      alpha_score_interval: alphaInterval,
      alpha_score_weight_zscore: alphaWeightZscore,
      alpha_score_weight_leadlag: alphaWeightLeadlag,
      alpha_score_weight_imbalance: alphaWeightImbalance,
      alpha_score_weight_funding: alphaWeightFunding,
      alpha_score_threshold: alphaThreshold,
      alpha_score_zscore_window: aZscoreW,
      alpha_score_leadlag_window: aLeadlagW,
      alpha_score_hurst_lookback: aHurstLB,
      alpha_score_hurst_trending: alphaHurstTrending,
      alpha_score_hurst_reverting: alphaHurstReverting,
      alpha_score_atr_mult_btc: alphaAtrMultBtc,
      alpha_score_atr_mult_xrp: alphaAtrMultXrp,
      alpha_score_stop_resume_n: aResumeN,
    });
  };

  if (isLoading) {
    return <div className="settings"><div className="settings-loading">Lade Settings...</div></div>;
  }

  return (
    <div className="settings">
      <div className="settings-header">
        <h2>Settings</h2>
        <p>Konfigurierbare Parameter fuer Order-Erstellung und Trading.</p>
      </div>

      {message && (
        <div className={`settings-message settings-${message.type}`}>
          {message.text}
          <button className="settings-message-close" onClick={dismissMessage}>&times;</button>
        </div>
      )}

      <div className="settings-section">
        <h3>Order-Limits</h3>

        <div className="settings-field">
          <label className="settings-label">Maximaler Order-Wert</label>
          <div className="settings-input-group">
            <input
              type="number"
              value={maxOrderValueEur}
              onChange={(e) => setMaxOrderValueEur(e.target.value)}
              min="0"
              step="100"
            />
            <span className="settings-unit">EUR</span>
          </div>
          <div className="settings-hint">
            Einzelne Orders werden abgelehnt wenn der Gegenwert (BTC * Preis) diesen Betrag ueberschreitet.
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h3>Makro-Signal</h3>

        <div className="settings-field">
          <label className="settings-label">Signal-Intervall</label>
          <div className="settings-interval-group">
            {[
              { value: '1', label: '1 Min', desc: 'Schnell, mehr Rauschen' },
              { value: '5', label: '5 Min', desc: 'Ausgewogen' },
              { value: '15', label: '15 Min', desc: 'Stabiler, weniger Signale' },
            ].map(({ value, label }) => (
              <button
                key={value}
                className={`interval-btn ${macroSignalInterval === value ? 'interval-active' : ''}`}
                onClick={() => setMacroSignalInterval(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <div className="settings-hint">
            Kuerzere Intervalle zeigen schnellere Bewegungen, haben aber angepasste (kleinere) Schwellenwerte.
            Schwellenwerte skalieren mit sqrt(Intervall) - z.B. sind 1-Min-Schwellen ~26% der 15-Min-Werte.
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h3>Sell-Allocation Strategie</h3>

        <div className="settings-field">
          <label className="settings-label">Standard-Allokation bei Verkaeufen</label>
          <div className="settings-interval-group">
            {[
              { value: 'FIFO', label: 'FIFO' },
              { value: 'LIFO', label: 'LIFO' },
              { value: 'HIGHEST_COST', label: 'Hoechste Kosten' },
            ].map(({ value, label }) => (
              <button
                key={value}
                className={`interval-btn ${sellAllocationStrategy === value ? 'interval-active' : ''}`}
                onClick={() => setSellAllocationStrategy(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <div className="settings-hint">
            FIFO: Aelteste Lots zuerst schliessen (Standard, steuerlich oft vorteilhaft).
            LIFO: Neueste Lots zuerst schliessen.
            Hoechste Kosten: Lots mit hoechstem Break-even zuerst (minimiert realisierte Gewinne).
            Gilt nur fuer Verkaeufe ohne explizite Lot-/Pairing-Zuordnung.
          </div>
        </div>
      </div>

      <div className="settings-section settings-section-alpha">
        <h3>Alpha Score</h3>

        {/* Essential Settings */}
        <div className="settings-field">
          <label className="settings-label">Kerzen-Intervall</label>
          <div className="settings-interval-group">
            {[
              { value: '5m', label: '5 Min' },
              { value: '15m', label: '15 Min' },
              { value: '1h', label: '1 Std' },
            ].map(({ value, label }) => (
              <button
                key={value}
                className={`interval-btn ${alphaInterval === value ? 'interval-active' : ''}`}
                onClick={() => setAlphaInterval(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <div className="settings-hint">
            Zeitrahmen fuer Alpha Score Berechnung. 15m bietet das beste Verhaeltnis aus Reaktionsgeschwindigkeit und Signalqualitaet.
          </div>
        </div>

        <div className="settings-field">
          <label className="settings-label">Faktor-Gewichte</label>
          <div className="settings-weight-group">
            <div className="settings-weight-item">
              <span className="settings-weight-label">Z-Score</span>
              <input
                type="number"
                value={alphaWeightZscore}
                onChange={(e) => setAlphaWeightZscore(e.target.value)}
                min="0"
                max="100"
                step="1"
              />
              <span className="settings-weight-pct">{normalizeWeight(alphaWeightZscore)}%</span>
            </div>
            <div className="settings-weight-item">
              <span className="settings-weight-label">Lead-Lag</span>
              <input
                type="number"
                value={alphaWeightLeadlag}
                onChange={(e) => setAlphaWeightLeadlag(e.target.value)}
                min="0"
                max="100"
                step="1"
              />
              <span className="settings-weight-pct">{normalizeWeight(alphaWeightLeadlag)}%</span>
            </div>
            <div className="settings-weight-item">
              <span className="settings-weight-label">Orderbook</span>
              <input
                type="number"
                value={alphaWeightImbalance}
                onChange={(e) => setAlphaWeightImbalance(e.target.value)}
                min="0"
                max="100"
                step="1"
              />
              <span className="settings-weight-pct">{normalizeWeight(alphaWeightImbalance)}%</span>
            </div>
            <div className="settings-weight-item">
              <span className="settings-weight-label">Funding</span>
              <input
                type="number"
                value={alphaWeightFunding}
                onChange={(e) => setAlphaWeightFunding(e.target.value)}
                min="0"
                max="100"
                step="1"
              />
              <span className="settings-weight-pct">{normalizeWeight(alphaWeightFunding)}%</span>
            </div>
          </div>
          <div className="settings-weight-note">
            Gewichte werden automatisch auf 100% normalisiert beim Speichern.
          </div>
        </div>

        <div className="settings-field">
          <label className="settings-label">Signal-Schwelle</label>
          <div className="settings-input-group">
            <input
              type="number"
              value={alphaThreshold}
              onChange={(e) => setAlphaThreshold(e.target.value)}
              min="0.1"
              max="5.0"
              step="0.1"
            />
            <span className="settings-unit">Score</span>
          </div>
          <div className="settings-hint">
            Score &gt;= Schwelle = Signal. Hoeher = weniger, aber staerkere Signale. Standard: 3.0
          </div>
        </div>

        {/* Advanced Settings Toggle */}
        <button
          className="settings-advanced-toggle"
          onClick={() => setAdvancedOpen(!advancedOpen)}
          type="button"
        >
          {advancedOpen ? 'Erweiterte Einstellungen verbergen' : 'Erweiterte Einstellungen anzeigen'}
          <span className={`settings-toggle-arrow ${advancedOpen ? 'open' : ''}`}>&#9662;</span>
        </button>

        <div className={`settings-advanced-content ${advancedOpen ? 'open' : ''}`}>
          <div className="settings-field">
            <label className="settings-label">Z-Score Window</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaZscoreWindow}
                onChange={(e) => setAlphaZscoreWindow(e.target.value)}
                min="10"
                max="500"
                step="10"
              />
              <span className="settings-unit">Kerzen</span>
            </div>
            <div className="settings-hint">
              Rolling Window fuer Z-Score Berechnung (Mean Reversion). Standard: 60
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label">Lead-Lag Window</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaLeadlagWindow}
                onChange={(e) => setAlphaLeadlagWindow(e.target.value)}
                min="10"
                max="500"
                step="10"
              />
              <span className="settings-unit">Kerzen</span>
            </div>
            <div className="settings-hint">
              Rolling Window fuer Lead-Lag Cross-Correlation. Standard: 30
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label">Hurst Lookback</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaHurstLookback}
                onChange={(e) => setAlphaHurstLookback(e.target.value)}
                min="10"
                max="500"
                step="10"
              />
              <span className="settings-unit">Kerzen</span>
            </div>
            <div className="settings-hint">
              Datenpunkte fuer Hurst-Exponent Berechnung (Regime-Erkennung). Standard: 100
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label">Hurst Trending-Schwelle</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaHurstTrending}
                onChange={(e) => setAlphaHurstTrending(e.target.value)}
                min="0"
                max="1"
                step="0.01"
              />
            </div>
            <div className="settings-hint">
              H &gt; Schwelle = Trending-Regime (Z-Score Gewicht wird reduziert). Standard: 0.55
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label">Hurst Mean-Reverting-Schwelle</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaHurstReverting}
                onChange={(e) => setAlphaHurstReverting(e.target.value)}
                min="0"
                max="1"
                step="0.01"
              />
            </div>
            <div className="settings-hint">
              H &lt; Schwelle = Mean-Reverting-Regime (Z-Score behaelt volles Gewicht). Standard: 0.45
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label">ATR Multiplikator BTC</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaAtrMultBtc}
                onChange={(e) => setAlphaAtrMultBtc(e.target.value)}
                min="0.5"
                max="10"
                step="0.5"
              />
              <span className="settings-unit">x ATR</span>
            </div>
            <div className="settings-hint">
              Trailing-Stop Abstand fuer BTC-Positionen. Standard: 2.0
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label">ATR Multiplikator XRP</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaAtrMultXrp}
                onChange={(e) => setAlphaAtrMultXrp(e.target.value)}
                min="0.5"
                max="10"
                step="0.5"
              />
              <span className="settings-unit">x ATR</span>
            </div>
            <div className="settings-hint">
              Trailing-Stop Abstand fuer XRP-Positionen (hoeher wegen hoeherer Volatilitaet). Standard: 3.0
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label">Datenpunkte bis Wiederaufnahme</label>
            <div className="settings-input-group">
              <input
                type="number"
                value={alphaStopResumeN}
                onChange={(e) => setAlphaStopResumeN(e.target.value)}
                min="1"
                max="50"
                step="1"
              />
              <span className="settings-unit">Datenpunkte</span>
            </div>
            <div className="settings-hint">
              Konsekutive frische Datenpunkte bis Trailing Stop nach Freeze wieder aktiv wird. Standard: 5
            </div>
          </div>
        </div>

        <button
          className="settings-reset-btn"
          onClick={handleResetAlphaDefaults}
          type="button"
        >
          Alpha Score Defaults wiederherstellen
        </button>
      </div>

      <div className="settings-section">
        <h3>Orderblock Detection</h3>

        <div className="settings-field">
          <label className="settings-label">Timeframe</label>
          <div className="settings-interval-group">
            {[
              { value: '1h', label: '1h' },
              { value: '4h', label: '4h' },
              { value: '1d', label: '1d' },
            ].map(({ value, label }) => (
              <button
                key={value}
                className={`interval-btn ${obInterval === value ? 'interval-active' : ''}`}
                onClick={() => setObInterval(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <div className="settings-hint">
            Kerzen-Zeitrahmen fuer Orderblock-Erkennung. 4h bietet das beste Verhaeltnis aus Signalqualitaet und Rauschen.
          </div>
        </div>

        <div className="settings-field">
          <label className="settings-label">ATR Multiplikator</label>
          <div className="settings-input-group">
            <input
              type="number"
              value={obAtrMultiplier}
              onChange={(e) => setObAtrMultiplier(e.target.value)}
              min="0.5"
              max="10"
              step="0.5"
            />
            <span className="settings-unit">x ATR</span>
          </div>
          <div className="settings-hint">
            Mindest-Displacement fuer OB-Validierung. Hoeher = weniger, aber staerkere Zonen.
          </div>
        </div>

        <div className="settings-field">
          <label className="settings-label">Target Risk:Reward</label>
          <div className="settings-input-group">
            <input
              type="number"
              value={obTargetRr}
              onChange={(e) => setObTargetRr(e.target.value)}
              min="0.5"
              max="10"
              step="0.5"
            />
            <span className="settings-unit">R:R</span>
          </div>
          <div className="settings-hint">
            Ziel-Verhaeltnis Gewinn zu Risiko. 2.0 = Target ist doppelt so weit wie Stop.
          </div>
        </div>

        <div className="settings-field">
          <label className="settings-label">Impulse Window</label>
          <div className="settings-input-group">
            <input
              type="number"
              value={obImpulseWindow}
              onChange={(e) => setObImpulseWindow(e.target.value)}
              min="2"
              max="20"
              step="1"
            />
            <span className="settings-unit">Kerzen</span>
          </div>
          <div className="settings-hint">
            Max. Kerzen nach Basiskerze fuer Displacement/FVG/BOS. Empfohlen: 5 (4h), 8 (1h), 3 (1d).
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h3>Reconciliation Toleranzen</h3>

        <div className="settings-field">
          <label className="settings-label">Base-Asset Toleranz (z.B. BTC)</label>
          <div className="settings-input-group">
            <input
              type="text"
              value={reconToleranceBase}
              onChange={(e) => setReconToleranceBase(e.target.value)}
              placeholder="0.0001"
            />
            <span className="settings-unit">BTC</span>
          </div>
          <div className="settings-hint">
            Maximale Abweichung zwischen Binance- und berechneter Base-Asset-Balance,
            ab der ein Alert erzeugt wird. 0.0001 BTC = ca. 8-10 EUR bei aktuellen Kursen.
          </div>
        </div>

        <div className="settings-field">
          <label className="settings-label">Quote-Asset Toleranz (z.B. EUR)</label>
          <div className="settings-input-group">
            <input
              type="text"
              value={reconToleranceQuote}
              onChange={(e) => setReconToleranceQuote(e.target.value)}
              placeholder="1.00"
            />
            <span className="settings-unit">EUR</span>
          </div>
          <div className="settings-hint">
            Maximale Abweichung zwischen Binance- und berechneter Quote-Asset-Balance.
            Differenzen darueber erzeugen Warning-Alerts, &gt;10x Toleranz erzeugt Critical-Alerts.
          </div>
        </div>
      </div>

      <div className="settings-actions">
        <button
          className="btn-settings-save"
          onClick={handleSave}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Speichern...' : 'Speichern'}
        </button>
      </div>
    </div>
  );
};

export default Settings;
