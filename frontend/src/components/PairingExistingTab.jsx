/**
 * PairingExistingTab - Tab "Bestehende Pairings" mit Lifecycle-Management
 *
 * Verwaltet: Filter, Queries, Mutations (Lock/Unlock/Execute/Delete),
 * Simulation-State + SimulationModal
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  simulatePairing,
  listPairings,
  lockPairing,
  unlockPairing,
  executePairing,
  deletePairing,
} from '../api/client';
import { formatNumber, formatEUR } from '../utils/formatters';
import { useAppState } from '../contexts/AppStateContext';
import SimulationModal from './SimulationModal';

const PairingExistingTab = ({ onHighlightLots, showMessage }) => {
  const { userId, marketPrice } = useAppState();
  const queryClient = useQueryClient();

  const [existingStatusFilter, setExistingStatusFilter] = useState(null);
  const [showExecuted, setShowExecuted] = useState(false);

  // Simulation-State pro Pairing (verhindert Race Conditions bei parallelen Simulationen)
  const [simulationsByPairingId, setSimulationsByPairingId] = useState({});
  const [activePairingId, setActivePairingId] = useState(null);
  const [showSimulationModal, setShowSimulationModal] = useState(false);
  const [simulatingPairingId, setSimulatingPairingId] = useState(null);

  // ─── Query ───

  const {
    data: existingData,
    isLoading: existingLoading,
    refetch: refetchExisting,
  } = useQuery({
    queryKey: ['pairings', userId, existingStatusFilter],
    queryFn: () => listPairings(userId, existingStatusFilter),
  });

  // ─── Mutations ───

  const lockMutation = useMutation({
    mutationFn: (pairingId) => lockPairing(userId, pairingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      showMessage('success', 'Pairing gesperrt (LOCKED)');
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const unlockMutation = useMutation({
    mutationFn: (pairingId) => unlockPairing(userId, pairingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      showMessage('success', 'Pairing entsperrt (DRAFT)');
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const executeMutation = useMutation({
    mutationFn: ({ pairingId, sellPrice }) => executePairing(userId, pairingId, marketPrice, 0.002, sellPrice),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      queryClient.invalidateQueries({ queryKey: ['lots'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      setSimulationsByPairingId({});
      setActivePairingId(null);
      const lotCount = data?.lot_count || 0;
      showMessage('success', `Pairing ausgefuehrt: 1 Order (${lotCount} Lots aggregiert) auf Binance platziert`);
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (pairingId) => deletePairing(userId, pairingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pairings'] });
      setSimulationsByPairingId({});
      setActivePairingId(null);
      showMessage('success', 'Pairing gelöscht');
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  // ─── Handlers ───

  const handleSimulate = async (pairingId, sellPrice = null) => {
    setSimulatingPairingId(pairingId);
    try {
      const result = await simulatePairing(userId, pairingId, marketPrice, 0.001, 0.002, sellPrice);
      setSimulationsByPairingId(prev => ({
        ...prev,
        [pairingId]: { data: { ...result, pairing_id: pairingId }, sellPrice },
      }));
      setActivePairingId(pairingId);
      setShowSimulationModal(true);
    } catch (error) {
      showMessage('error', error.response?.data?.detail || error.message);
    } finally {
      setSimulatingPairingId(null);
    }
  };

  const handleResimulate = async (newPrice) => {
    if (!activePairingId) return;
    await handleSimulate(activePairingId, newPrice);
  };

  const handleExecute = (pairingId) => {
    const sim = simulationsByPairingId[pairingId];
    if (!sim) {
      showMessage('error', 'Bitte zuerst Simulation durchführen!');
      return;
    }
    if (window.confirm('Pairing wirklich ausführen? Orders werden auf Binance platziert.')) {
      executeMutation.mutate({ pairingId, sellPrice: sim.sellPrice });
    }
  };

  // ─── Render ───

  return (
    <div className="pairing-tab-content">
      <div className="pairing-controls">
        <div className="filter-group">
          <span className="filter-label">Status</span>
          <select
            value={existingStatusFilter || ''}
            onChange={(e) => setExistingStatusFilter(e.target.value || null)}
            style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, minHeight: 38, background: 'white', cursor: 'pointer' }}
          >
            <option value="">Alle</option>
            <option value="DRAFT">Draft</option>
            <option value="LOCKED">Locked</option>
            <option value="EXECUTED">Executed</option>
          </select>
        </div>
        <label className="toggle-label">
          <span className="toggle-switch">
            <input
              type="checkbox"
              checked={showExecuted}
              onChange={(e) => setShowExecuted(e.target.checked)}
            />
            <span className="toggle-slider" />
          </span>
          Ausgeführte anzeigen
        </label>
        <button className="btn-refresh" onClick={() => refetchExisting()}>
          Neu laden
        </button>
      </div>

      {existingLoading ? (
        <div className="pairing-empty">Lade Pairings...</div>
      ) : (() => {
        const filtered = (existingData?.pairings || []).filter(
          (p) => showExecuted || p.status !== 'EXECUTED'
        );
        return filtered.length === 0 ? (
          <div className="pairing-empty">Keine Pairings vorhanden.</div>
        ) : (
        <div className="pairing-cards">
          {filtered.map((p) => (
            <div
              key={p.id}
              className={`pairing-card ${p.status.toLowerCase()}`}
              onMouseEnter={() => onHighlightLots(new Set(p.items.map((item) => item.lot_id)))}
              onMouseLeave={() => onHighlightLots(new Set())}
            >
              <div className="pairing-card-header">
                <span className="pairing-card-title">
                  <span className={`status-badge ${p.status.toLowerCase()}`}>
                    {p.status}
                  </span>
                  {p.items.length} Lots
                </span>
                <span className="pairing-pnl">
                  {formatNumber(parseFloat(p.threshold_pct) * 100)}%
                </span>
              </div>
              <div className="pairing-card-details">
                <div>
                  <span className="label">Netto BTC</span><br />
                  {formatNumber(p.net_qty_btc, 8)}
                </div>
                <div>
                  <span className="label">Netto Kosten</span><br />
                  {formatEUR(p.net_cost)}
                </div>
                {p.created_at && (
                  <div>
                    <span className="label">Erstellt</span><br />
                    {new Date(p.created_at).toLocaleDateString('de-DE')}
                  </div>
                )}
              </div>
              <div className="pairing-card-lots">
                {p.items.map((item) => (
                  <span key={item.lot_id} className="lot-chip" title={item.lot_id}>
                    {item.lot_id.slice(0, 8)}...
                  </span>
                ))}
              </div>
              <div className="pairing-card-actions">
                {p.status === 'DRAFT' && (
                  <>
                    <button
                      className="btn-simulate"
                      onClick={() => handleSimulate(p.id, simulationsByPairingId[p.id]?.sellPrice || null)}
                      disabled={simulatingPairingId === p.id}
                    >
                      {simulatingPairingId === p.id ? 'Simuliere...' : 'Simulation'}
                    </button>
                    <button
                      className="btn-lock"
                      onClick={() => lockMutation.mutate(p.id)}
                      disabled={lockMutation.isPending}
                    >
                      Sperren
                    </button>
                    <button
                      className="btn-delete"
                      onClick={() => {
                        if (window.confirm('Pairing wirklich löschen?')) {
                          deleteMutation.mutate(p.id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
                    >
                      Löschen
                    </button>
                  </>
                )}
                {p.status === 'LOCKED' && (
                  <>
                    <button
                      className="btn-simulate"
                      onClick={() => handleSimulate(p.id, simulationsByPairingId[p.id]?.sellPrice || null)}
                      disabled={simulatingPairingId === p.id}
                    >
                      {simulatingPairingId === p.id ? 'Simuliere...' : 'Simulation ansehen'}
                    </button>
                    <button
                      className="btn-unlock"
                      onClick={() => unlockMutation.mutate(p.id)}
                      disabled={unlockMutation.isPending}
                    >
                      {unlockMutation.isPending ? 'Entsperre...' : 'Entsperren'}
                    </button>
                    <button
                      className="btn-execute"
                      onClick={() => handleExecute(p.id)}
                      disabled={executeMutation.isPending}
                    >
                      {executeMutation.isPending ? 'Ausführen...' : 'Ausführen'}
                    </button>
                  </>
                )}
                {p.status === 'EXECUTED' && (
                  <span className="executed-label">Ausgeführt</span>
                )}
              </div>
            </div>
          ))}
        </div>
        );
      })()}

      {activePairingId && simulationsByPairingId[activePairingId] && showSimulationModal && (
        <SimulationModal
          simulationData={simulationsByPairingId[activePairingId].data}
          onClose={() => setShowSimulationModal(false)}
          onResimulate={handleResimulate}
        />
      )}
    </div>
  );
};

export default PairingExistingTab;
