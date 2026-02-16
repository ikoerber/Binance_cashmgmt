import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSettings, updateSettings } from '../api/client';
import './Settings.css';

const Settings = ({ userId = 'user_123' }) => {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState(null);
  const [maxOrderValueEur, setMaxOrderValueEur] = useState('');
  const [macroSignalInterval, setMacroSignalInterval] = useState('15');
  const [sellAllocationStrategy, setSellAllocationStrategy] = useState('FIFO');
  const [obInterval, setObInterval] = useState('4h');
  const [obAtrMultiplier, setObAtrMultiplier] = useState('2.0');
  const [obTargetRr, setObTargetRr] = useState('2.0');
  const [obImpulseWindow, setObImpulseWindow] = useState('5');

  const showMessage = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

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
    saveMutation.mutate({
      max_order_value_eur: value,
      macro_signal_interval: macroSignalInterval,
      sell_allocation_strategy: sellAllocationStrategy,
      ob_interval: obInterval,
      ob_atr_multiplier: atrMult,
      ob_target_rr: targetRr,
      ob_impulse_window: impulseW,
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
          <button className="settings-message-close" onClick={() => setMessage(null)}>&times;</button>
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
