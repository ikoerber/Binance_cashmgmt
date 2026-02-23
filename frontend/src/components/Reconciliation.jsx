import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  runFullReconciliation,
  reconcileOrders,
  reconcileBalances,
  reconcileFills,
  getReconciliationHistory,
  getReconciliationRunDetail,
} from '../api/client';
import { formatNumber, formatQuote, formatBase, formatDate, formatTime } from '../utils/formatters';
import { getBaseLabel, getQuoteLabel } from '../utils/symbolRegistry';
import { useSymbol } from '../contexts/SymbolContext';
import { useUser } from '../contexts/UserContext';
import useNotification from '../hooks/useNotification';
import './Reconciliation.css';

const ErrorBanner = ({ errors }) => (
  <div className="recon-errors">
    {errors.map((err, idx) => (
      <div key={idx} className="recon-error-item">{err}</div>
    ))}
  </div>
);

const BalanceCard = ({ asset, data, formatFn }) => (
  <div className="balance-card">
    <div className="balance-card-title">{asset}</div>
    <div className="balance-row">
      <span className="balance-label">Binance</span>
      <span className="balance-value">{formatFn(data.binance)}</span>
    </div>
    <div className="balance-row">
      <span className="balance-label">Berechnet</span>
      <span className="balance-value">{formatFn(data.calculated)}</span>
    </div>
    <div className="balance-row diff">
      <span className="balance-label">Differenz</span>
      <span className="balance-value">
        {formatFn(data.diff)}
        <span className={`balance-tolerance ${data.within_tolerance ? 'ok' : 'warning'}`}>
          {data.within_tolerance ? 'OK' : 'Abweichung'}
        </span>
      </span>
    </div>
  </div>
);

const BalancesSection = ({ report, activeSymbol }) => {
  if (!report) return null;
  const baseLabel = getBaseLabel(activeSymbol);
  const quoteLabel = getQuoteLabel(activeSymbol);
  return (
    <div className="recon-section">
      <div className="recon-section-header">
        <h3>Balances</h3>
        <span className={`recon-status-badge ${report.within_tolerance ? 'ok' : 'warning'}`}>
          {report.within_tolerance ? 'OK' : 'Abweichung'}
        </span>
      </div>
      {report.errors?.length > 0 && <ErrorBanner errors={report.errors} />}
      <div className="balance-comparison-grid">
        <BalanceCard asset={baseLabel} data={report.base} formatFn={(v) => formatBase(v, activeSymbol)} />
        <BalanceCard asset={quoteLabel} data={report.quote} formatFn={(v) => formatQuote(v, activeSymbol)} />
      </div>
    </div>
  );
};

const OrdersSection = ({ report }) => {
  if (!report) return null;
  return (
    <div className="recon-section">
      <div className="recon-section-header">
        <h3>Orders</h3>
        <span className={`recon-status-badge ${report.discrepancies?.length === 0 ? 'ok' : 'warning'}`}>
          {report.discrepancies?.length === 0 ? 'OK' : `${report.discrepancies.length} Diskrepanzen`}
        </span>
      </div>
      {report.errors?.length > 0 && <ErrorBanner errors={report.errors} />}
      <div className="recon-summary-row">
        <div className="recon-stat">
          <span className="recon-stat-label">Synchronisiert</span>
          <span className="recon-stat-value">{report.synced}</span>
        </div>
        <div className="recon-stat">
          <span className="recon-stat-label">Status aktualisiert</span>
          <span className="recon-stat-value">{report.status_updated}</span>
        </div>
        <div className="recon-stat">
          <span className="recon-stat-label">Diskrepanzen</span>
          <span className="recon-stat-value">{report.discrepancies?.length ?? 0}</span>
        </div>
      </div>
      {report.discrepancies?.length > 0 && (
        <table className="recon-discrepancy-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Client Order ID</th>
              <th>Binance Order ID</th>
              <th>Problem</th>
            </tr>
          </thead>
          <tbody>
            {report.discrepancies.map((d, idx) => (
              <tr key={idx}>
                <td className="order-id">{d.order_id || '-'}</td>
                <td className="order-id">{d.client_order_id || '-'}</td>
                <td className="order-id">{d.binance_order_id || '-'}</td>
                <td className="issue-text">{d.issue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

const FillsSection = ({ report }) => {
  if (!report) return null;
  return (
    <div className="recon-section">
      <div className="recon-section-header">
        <h3>Fills</h3>
        <span className={`recon-status-badge ${report.errors?.length === 0 ? 'ok' : 'warning'}`}>
          {report.errors?.length === 0 ? 'OK' : 'Fehler'}
        </span>
      </div>
      {report.errors?.length > 0 && <ErrorBanner errors={report.errors} />}
      <div className="recon-summary-row">
        <div className="recon-stat">
          <span className="recon-stat-label">Neue Fills</span>
          <span className="recon-stat-value">{report.new_fills}</span>
        </div>
        <div className="recon-stat">
          <span className="recon-stat-label">Neue Lots</span>
          <span className="recon-stat-value">{report.new_lots}</span>
        </div>
        <div className="recon-stat">
          <span className="recon-stat-label">Allocations</span>
          <span className="recon-stat-value">{report.allocations}</span>
        </div>
      </div>
    </div>
  );
};

const TRIGGER_LABELS = {
  manual: 'Manuell',
  post_sync: 'Nach Sync',
  post_full_sync: 'Nach Voll-Sync',
};

const TRIGGER_CLASSES = {
  manual: 'slate',
  post_sync: 'orange',
  post_full_sync: 'orange',
};

const STATUS_CLASSES = {
  completed: 'green',
  partial: 'amber',
  failed: 'red',
};

const STATUS_LABELS = {
  completed: 'Abgeschlossen',
  partial: 'Teilweise',
  failed: 'Fehlgeschlagen',
};

const SEVERITY_CLASSES = {
  critical: 'red',
  warning: 'amber',
  info: 'blue',
};

const ReconHistorySection = ({ userId, expandedRunId, setExpandedRunId }) => {
  const { data: historyData } = useQuery({
    queryKey: ['reconciliation-history', userId],
    queryFn: () => getReconciliationHistory(userId, 10, 0),
    staleTime: 60 * 1000,
  });

  const { data: runDetail } = useQuery({
    queryKey: ['reconciliation-run', expandedRunId],
    queryFn: () => getReconciliationRunDetail(userId, expandedRunId),
    enabled: !!expandedRunId,
  });

  const runs = historyData?.runs ?? [];

  if (runs.length === 0) {
    return (
      <div className="recon-section">
        <div className="recon-section-header">
          <h3>Reconciliation-Historie</h3>
        </div>
        <p className="recon-history-empty">Keine vergangenen Runs.</p>
      </div>
    );
  }

  return (
    <div className="recon-section">
      <div className="recon-section-header">
        <h3>Reconciliation-Historie</h3>
        <span className="recon-status-badge ok">{runs.length} Runs</span>
      </div>
      <table className="recon-history-table">
        <thead>
          <tr>
            <th>Zeitpunkt</th>
            <th>Trigger</th>
            <th>Status</th>
            <th>Diskrepanzen</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const isExpanded = expandedRunId === run.id;
            const alertCount = run.alert_count ?? 0;
            return (
              <React.Fragment key={run.id}>
                <tr
                  className={`recon-history-row ${isExpanded ? 'expanded' : ''}`}
                  onClick={() => setExpandedRunId(isExpanded ? null : run.id)}
                >
                  <td>
                    {formatDate(run.created_at)} {formatTime(run.created_at)}
                  </td>
                  <td>
                    <span className={`recon-trigger-badge ${TRIGGER_CLASSES[run.trigger] || 'slate'}`}>
                      {TRIGGER_LABELS[run.trigger] || run.trigger}
                    </span>
                  </td>
                  <td>
                    <span className={`recon-status-badge-small ${STATUS_CLASSES[run.status] || 'slate'}`}>
                      {STATUS_LABELS[run.status] || run.status}
                    </span>
                  </td>
                  <td>
                    {run.has_discrepancies ? (
                      <span className="recon-discrepancy-count">{alertCount}</span>
                    ) : (
                      <span className="recon-check-ok">--</span>
                    )}
                  </td>
                  <td className="recon-expand-toggle">
                    {isExpanded ? '\u25B2' : '\u25BC'}
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="recon-history-detail-row">
                    <td colSpan={5}>
                      <div className="recon-history-detail">
                        {runDetail?.alerts?.length > 0 ? (
                          runDetail.alerts.map((alert) => (
                            <div
                              key={alert.id}
                              className={`recon-alert-item ${SEVERITY_CLASSES[alert.severity] || 'blue'}`}
                            >
                              <span className={`recon-alert-severity ${SEVERITY_CLASSES[alert.severity] || 'blue'}`}>
                                {alert.severity?.toUpperCase()}
                              </span>
                              <span className="recon-alert-title">{alert.title}</span>
                              {alert.details_json && (
                                <span className="recon-alert-details">
                                  {typeof alert.details_json === 'object'
                                    ? Object.entries(alert.details_json)
                                        .map(([k, v]) => `${k}: ${v}`)
                                        .join(' | ')
                                    : String(alert.details_json)}
                                </span>
                              )}
                            </div>
                          ))
                        ) : (
                          <div className="recon-alert-item blue">
                            <span className="recon-alert-title">Keine Alerts fuer diesen Run.</span>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const Reconciliation = () => {
  const { userId } = useUser();
  const { symbol: activeSymbol } = useSymbol();
  const queryClient = useQueryClient();
  const { message, showMessage, dismissMessage } = useNotification();
  const [lastRunTime, setLastRunTime] = useState(null);
  const [expandedRunId, setExpandedRunId] = useState(null);

  const onReconSuccess = () => {
    setLastRunTime(new Date());
    queryClient.invalidateQueries({ queryKey: ['lots'] });
    queryClient.invalidateQueries({ queryKey: ['portfolio'] });
    queryClient.invalidateQueries({ queryKey: ['orders'] });
    queryClient.invalidateQueries({ queryKey: ['reconciliation-history'] });
  };

  const fullMutation = useMutation({
    mutationFn: () => runFullReconciliation(userId, activeSymbol),
    onSuccess: () => {
      showMessage('success', 'Vollständige Reconciliation abgeschlossen.');
      onReconSuccess();
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const ordersMutation = useMutation({
    mutationFn: () => reconcileOrders(userId, activeSymbol),
    onSuccess: () => {
      showMessage('success', 'Order-Reconciliation abgeschlossen.');
      onReconSuccess();
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const balancesMutation = useMutation({
    mutationFn: () => reconcileBalances(userId, activeSymbol),
    onSuccess: () => {
      showMessage('success', 'Balance-Reconciliation abgeschlossen.');
      onReconSuccess();
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const fillsMutation = useMutation({
    mutationFn: () => reconcileFills(userId, activeSymbol),
    onSuccess: () => {
      showMessage('success', 'Fills-Reconciliation abgeschlossen.');
      onReconSuccess();
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const anyPending =
    fullMutation.isPending ||
    ordersMutation.isPending ||
    balancesMutation.isPending ||
    fillsMutation.isPending;

  const currentReport = useMemo(() => {
    const full = fullMutation.data?.report;
    return {
      orders: ordersMutation.data?.report || full?.orders || null,
      balances: balancesMutation.data?.report || full?.balances || null,
      fills: fillsMutation.data?.report || full?.fills || null,
    };
  }, [fullMutation.data, ordersMutation.data, balancesMutation.data, fillsMutation.data]);

  const hasAnyResult = currentReport.orders || currentReport.balances || currentReport.fills;

  return (
    <div className="reconciliation">
      <div className="recon-header">
        <h2>Reconciliation</h2>
        <button
          className="btn-recon-full"
          onClick={() => fullMutation.mutate()}
          disabled={anyPending}
        >
          {fullMutation.isPending && <span className="recon-spinner" />}
          {fullMutation.isPending ? 'Reconciliation läuft...' : 'Vollständige Reconciliation'}
        </button>
      </div>

      {message && (
        <div className={`recon-message recon-${message.type}`}>
          {message.text}
          <button className="recon-message-close" onClick={dismissMessage}>&times;</button>
        </div>
      )}

      <div className="recon-actions">
        <button
          className="btn-recon-sub"
          onClick={() => ordersMutation.mutate()}
          disabled={anyPending}
        >
          {ordersMutation.isPending && <span className="recon-spinner" />}
          Orders abgleichen
        </button>
        <button
          className="btn-recon-sub"
          onClick={() => balancesMutation.mutate()}
          disabled={anyPending}
        >
          {balancesMutation.isPending && <span className="recon-spinner" />}
          Balances prüfen
        </button>
        <button
          className="btn-recon-sub"
          onClick={() => fillsMutation.mutate()}
          disabled={anyPending}
        >
          {fillsMutation.isPending && <span className="recon-spinner" />}
          Fills synchronisieren
        </button>
      </div>

      {hasAnyResult ? (
        <>
          <BalancesSection report={currentReport.balances} activeSymbol={activeSymbol} />
          <OrdersSection report={currentReport.orders} />
          <FillsSection report={currentReport.fills} />
        </>
      ) : (
        <div className="recon-empty">
          <p>Noch keine Reconciliation durchgeführt.</p>
          <p className="recon-empty-sub">
            Starte eine vollständige Reconciliation oder wähle einen einzelnen Bereich.
          </p>
        </div>
      )}

      <ReconHistorySection
        userId={userId}
        expandedRunId={expandedRunId}
        setExpandedRunId={setExpandedRunId}
      />

      {lastRunTime && (
        <div className="recon-last-run">
          Letzter Durchlauf: {lastRunTime.toLocaleTimeString('de-DE')}
        </div>
      )}
    </div>
  );
};

export default Reconciliation;
