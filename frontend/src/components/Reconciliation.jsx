import { useState, useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  runFullReconciliation,
  reconcileOrders,
  reconcileBalances,
  reconcileFills,
} from '../api/client';
import './Reconciliation.css';

const formatNumber = (num, decimals = 2) =>
  parseFloat(num).toLocaleString('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

const formatBTC = (num) => `${formatNumber(num, 8)} BTC`;
const formatEUR = (num) => `${formatNumber(num, 2)} \u20ac`;

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

const BalancesSection = ({ report }) => {
  if (!report) return null;
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
        <BalanceCard asset="BTC" data={report.btc} formatFn={formatBTC} />
        <BalanceCard asset="EUR" data={report.eur} formatFn={formatEUR} />
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

const Reconciliation = ({ userId = 'user_123' }) => {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState(null);
  const [lastRunTime, setLastRunTime] = useState(null);

  const showMessage = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const onReconSuccess = () => {
    setLastRunTime(new Date());
    queryClient.invalidateQueries({ queryKey: ['lots'] });
    queryClient.invalidateQueries({ queryKey: ['portfolio'] });
    queryClient.invalidateQueries({ queryKey: ['orders'] });
  };

  const fullMutation = useMutation({
    mutationFn: () => runFullReconciliation(userId),
    onSuccess: () => {
      showMessage('success', 'Vollständige Reconciliation abgeschlossen.');
      onReconSuccess();
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const ordersMutation = useMutation({
    mutationFn: () => reconcileOrders(userId),
    onSuccess: () => {
      showMessage('success', 'Order-Reconciliation abgeschlossen.');
      onReconSuccess();
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const balancesMutation = useMutation({
    mutationFn: () => reconcileBalances(userId),
    onSuccess: () => {
      showMessage('success', 'Balance-Reconciliation abgeschlossen.');
      onReconSuccess();
    },
    onError: (error) => {
      showMessage('error', error.response?.data?.detail || error.message);
    },
  });

  const fillsMutation = useMutation({
    mutationFn: () => reconcileFills(userId),
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
          <button className="recon-message-close" onClick={() => setMessage(null)}>&times;</button>
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
          <BalancesSection report={currentReport.balances} />
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

      {lastRunTime && (
        <div className="recon-last-run">
          Letzter Durchlauf: {lastRunTime.toLocaleTimeString('de-DE')}
        </div>
      )}
    </div>
  );
};

export default Reconciliation;
