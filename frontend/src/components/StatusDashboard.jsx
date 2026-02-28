/**
 * StatusDashboard - System Health Overview
 *
 * Displays the health status of all 8 backend services in a card grid.
 * Each card shows: service name, status badge (green/amber/red), detail,
 * last-checked timestamp, and relative age (e.g. "12s ago").
 *
 * Also displays WebSocket reconnect state when the connection is disrupted.
 *
 * Data source: GET /api/health/{user_id} (10s polling via TanStack Query)
 * WS state source: useWebSocket() context (reconnecting, attempts, lastError)
 */
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api/client';
import { useWebSocket } from '../contexts/WebSocketContext';
import './StatusDashboard.css';

const SERVICE_LABELS = {
  backend: 'Backend',
  db: 'Database',
  websocket: 'WebSocket',
  dry_run: 'Dry Run',
  alpha_score: 'Alpha Score',
  sentiment: 'Sentiment',
  macro: 'Macro Signal',
  binance_rest: 'Binance REST',
};

const STATUS_COLOR_MAP = {
  ok: 'green',
  stale: 'amber',
  degraded: 'amber',
  stopped: 'amber',
  unavailable: 'red',
  error: 'red',
};

const OVERALL_COLOR_MAP = {
  healthy: 'green',
  degraded: 'amber',
  critical: 'red',
};

const OVERALL_LABELS = {
  healthy: 'All Systems Operational',
  degraded: 'Partial Degradation',
  critical: 'Critical Issues',
};

/**
 * Format a timestamp as a relative age string.
 * @param {string} isoTimestamp - ISO 8601 timestamp
 * @param {number} now - Current time in ms (Date.now())
 * @returns {string} e.g. "12s ago", "3m ago", "2h ago", "never"
 */
function formatRelativeAge(isoTimestamp, now) {
  if (!isoTimestamp) return 'never';
  const seconds = Math.floor((now - new Date(isoTimestamp).getTime()) / 1000);
  if (seconds < 0) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

/**
 * Capitalize the first letter of a string.
 */
function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

const StatusDashboard = () => {
  const userId = 'user_123';

  const { data: health, isLoading, isError } = useQuery({
    queryKey: ['health', userId],
    queryFn: () => getHealth(userId),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });

  const { reconnecting, reconnectAttempts, lastError } = useWebSocket();

  // Ticking "now" state for relative age (updates every second)
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  if (isLoading) {
    return (
      <div className="status-dashboard">
        <h1>System Status</h1>
        <div className="loading">Lade System-Status...</div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="status-dashboard">
        <h1>System Status</h1>
        <div className="error">Fehler beim Laden des System-Status</div>
      </div>
    );
  }

  if (!health) return null;

  const overallColor = OVERALL_COLOR_MAP[health.overall_status] || 'amber';
  const overallLabel = OVERALL_LABELS[health.overall_status] || health.overall_status;

  const showWsAlert = reconnecting || (lastError && !reconnecting);

  return (
    <div className="status-dashboard">
      <h1>System Status</h1>

      {/* Overall status banner */}
      <div className={`status-overall overall-${overallColor}`}>
        <span className="status-overall-label">{overallLabel}</span>
        {health.checked_at && (
          <span className="status-overall-time">
            Checked: {new Date(health.checked_at).toLocaleString('de-DE')}
          </span>
        )}
      </div>

      {/* WebSocket reconnect alert */}
      {showWsAlert && (
        <div className="ws-reconnect-alert">
          <span className="ws-reconnect-title">WebSocket Reconnecting</span>
          {reconnectAttempts > 0 && (
            <span className="ws-attempts">Attempt: {reconnectAttempts}</span>
          )}
          {lastError && (
            <span className="ws-error">{lastError}</span>
          )}
        </div>
      )}

      {/* Service card grid */}
      <div className="status-grid">
        {Object.entries(health.services).map(([key, service]) => {
          const color = STATUS_COLOR_MAP[service.status] || 'amber';
          return (
            <div key={key} className={`status-card card-${color}`}>
              <div className="status-card-header">
                <span className="status-card-name">{SERVICE_LABELS[key] || key}</span>
                <span className={`status-badge status-${color}`}>
                  {capitalize(service.status)}
                </span>
              </div>
              {service.detail && (
                <div className="status-card-detail">{service.detail}</div>
              )}
              <div className="status-card-time">
                <span className="status-timestamp">
                  {service.last_checked
                    ? new Date(service.last_checked).toLocaleString('de-DE')
                    : 'Never'}
                </span>
                <span className="status-age">
                  {formatRelativeAge(service.last_checked, now)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default StatusDashboard;
