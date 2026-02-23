/**
 * AlertBanner - Persistent alert banner below navbar
 *
 * Fetches unacknowledged alerts from backend API, polls every 30s.
 * Renders severity-colored rows with dismiss/acknowledge functionality.
 * Visible on every page (rendered in App.jsx after GlobalNav).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAlerts, acknowledgeAlert, acknowledgeAllAlerts } from '../api/client';
import { useUser } from '../contexts/UserContext';
import './AlertBanner.css';

const SEVERITY_CONFIG = {
  critical: { icon: '\u26D4', label: 'Kritisch' },
  warning: { icon: '\u26A0', label: 'Warnung' },
  info: { icon: '\u2139', label: 'Info' },
};

const AlertBanner = () => {
  const { userId } = useUser();
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ['alerts', userId],
    queryFn: () => getAlerts(userId),
    refetchInterval: 30000,
    staleTime: 10000,
  });

  const dismissMutation = useMutation({
    mutationFn: (alertId) => acknowledgeAlert(alertId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });

  const dismissAllMutation = useMutation({
    mutationFn: () => acknowledgeAllAlerts(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });

  const alerts = data?.alerts || [];

  if (alerts.length === 0) {
    return null;
  }

  return (
    <div className="alert-banner">
      {alerts.map((alert) => {
        const severity = alert.severity || 'info';
        const config = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.info;

        return (
          <div key={alert.id} className={`alert-item ${severity}`}>
            <span className="alert-severity-icon" title={config.label}>
              {config.icon}
            </span>
            <span className="alert-title">{alert.title}</span>
            <button
              className="alert-dismiss"
              onClick={() => dismissMutation.mutate(alert.id)}
              disabled={dismissMutation.isPending}
              title="Bestaetigen"
            >
              &times;
            </button>
          </div>
        );
      })}

      {alerts.length > 1 && (
        <div className="alert-actions">
          <button
            className="btn-dismiss-all"
            onClick={() => dismissAllMutation.mutate()}
            disabled={dismissAllMutation.isPending}
          >
            {dismissAllMutation.isPending ? 'Wird bestaetigt...' : 'Alle bestaetigen'}
          </button>
        </div>
      )}
    </div>
  );
};

export default AlertBanner;
