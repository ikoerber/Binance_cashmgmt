/**
 * StatusDashboard.test.jsx
 *
 * Tests for the StatusDashboard component:
 * - DASH-01: 8 service cards with correct color-coding
 * - DASH-02: Last-checked timestamp and relative age
 * - DASH-03: WebSocket reconnect state display
 * - Loading/error/overall status states
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock useQuery from TanStack Query
const mockUseQuery = vi.fn();
vi.mock('@tanstack/react-query', () => ({
  useQuery: (...args) => mockUseQuery(...args),
}));

// Mock useWebSocket from WebSocketContext
const mockUseWebSocket = vi.fn();
vi.mock('../../contexts/WebSocketContext', () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

// Mock react-router-dom NavLink
vi.mock('react-router-dom', () => ({
  NavLink: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}));

import StatusDashboard from '../StatusDashboard';

const mockHealthData = {
  overall_status: 'degraded',
  services: {
    backend: { name: 'backend', status: 'ok', last_checked: '2026-02-28T10:00:00+00:00', detail: '' },
    db: { name: 'db', status: 'ok', last_checked: '2026-02-28T10:00:00+00:00', detail: '' },
    websocket: { name: 'websocket', status: 'degraded', last_checked: '2026-02-28T10:00:00+00:00', detail: 'No message for 95s' },
    dry_run: { name: 'dry_run', status: 'stopped', last_checked: '2026-02-28T10:00:00+00:00', detail: 'Dry run not running' },
    alpha_score: { name: 'alpha_score', status: 'ok', last_checked: '2026-02-28T10:00:00+00:00', detail: '' },
    sentiment: { name: 'sentiment', status: 'error', last_checked: '2026-02-28T10:00:00+00:00', detail: 'API timeout' },
    macro: { name: 'macro', status: 'stale', last_checked: '2026-02-28T10:00:00+00:00', detail: 'Cache expired' },
    binance_rest: { name: 'binance_rest', status: 'unavailable', last_checked: '2026-02-28T10:00:00+00:00', detail: 'Connection refused' },
  },
  checked_at: '2026-02-28T10:00:00+00:00',
};

describe('StatusDashboard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Default: connected, no reconnect
    mockUseWebSocket.mockReturnValue({
      connected: true,
      reconnecting: false,
      reconnectAttempts: 0,
      lastError: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // Test 1 (DASH-01): Renders 8 service cards with correct status color classes
  it('renders 8 service cards with correct color classes', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    // 8 service cards
    const cards = document.querySelectorAll('.status-card');
    expect(cards.length).toBe(8);

    // Check color classes: ok=green, degraded=amber, stopped=amber, error=red, stale=amber, unavailable=red
    expect(document.querySelector('.status-card.card-green')).toBeTruthy(); // backend (ok)
    expect(document.querySelector('.status-card.card-amber')).toBeTruthy(); // websocket (degraded) or dry_run (stopped) or macro (stale)
    expect(document.querySelector('.status-card.card-red')).toBeTruthy(); // sentiment (error) or binance_rest (unavailable)
  });

  // Test 2 (DASH-01): Status badges show human-readable status text
  it('shows human-readable status text in badges', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    expect(screen.getAllByText('Ok').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Degraded')).toBeInTheDocument();
    expect(screen.getByText('Stopped')).toBeInTheDocument();
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('Stale')).toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
  });

  // Test 3 (DASH-01): Service cards show human-readable service names
  it('shows human-readable service names', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    expect(screen.getByText('Backend')).toBeInTheDocument();
    expect(screen.getByText('Database')).toBeInTheDocument();
    expect(screen.getByText('WebSocket')).toBeInTheDocument();
    expect(screen.getByText('Dry Run')).toBeInTheDocument();
    expect(screen.getByText('Alpha Score')).toBeInTheDocument();
    expect(screen.getByText('Sentiment')).toBeInTheDocument();
    expect(screen.getByText('Macro Signal')).toBeInTheDocument();
    expect(screen.getByText('Binance REST')).toBeInTheDocument();
  });

  // Test 4 (DASH-02): Cards show last-checked timestamp
  it('shows last-checked timestamp in cards', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    // Timestamps should be rendered (localized format varies, just check presence)
    const timeElements = document.querySelectorAll('.status-card-time');
    expect(timeElements.length).toBe(8);
  });

  // Test 5 (DASH-02): Cards show relative age indicator
  it('shows relative age like "12s ago"', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    // Set system time 12 seconds after last_checked
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    // All cards have same last_checked, 12s before "now"
    const ageElements = document.querySelectorAll('.status-age');
    expect(ageElements.length).toBe(8);
    expect(ageElements[0].textContent).toBe('12s ago');
  });

  // Test 6 (DASH-03): WebSocket reconnect panel shown when reconnecting
  it('shows WebSocket reconnect panel when reconnecting', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    mockUseWebSocket.mockReturnValue({
      connected: false,
      reconnecting: true,
      reconnectAttempts: 3,
      lastError: 'Connection lost',
    });
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    const alert = document.querySelector('.ws-reconnect-alert');
    expect(alert).toBeTruthy();
    expect(screen.getByText(/3/)).toBeInTheDocument();
    expect(screen.getByText(/Connection lost/)).toBeInTheDocument();
  });

  // Test 7 (DASH-03): WebSocket reconnect panel hidden when connected
  it('hides WebSocket reconnect panel when connected', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    mockUseWebSocket.mockReturnValue({
      connected: true,
      reconnecting: false,
      reconnectAttempts: 0,
      lastError: null,
    });
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    const alert = document.querySelector('.ws-reconnect-alert');
    expect(alert).toBeNull();
  });

  // Test 8: Loading state renders loading indicator
  it('renders loading indicator while loading', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true, isError: false });

    render(<StatusDashboard />);

    expect(screen.getByText(/Lade System-Status/)).toBeInTheDocument();
  });

  // Test 9: Error state renders error message
  it('renders error message on error', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isError: true, error: { message: 'Network Error' } });

    render(<StatusDashboard />);

    expect(screen.getByText(/Fehler beim Laden des System-Status/)).toBeInTheDocument();
  });

  // Test 10: Overall status banner shows correct color/text
  it('shows overall status banner with correct color and text', () => {
    mockUseQuery.mockReturnValue({ data: mockHealthData, isLoading: false, isError: false });
    vi.setSystemTime(new Date('2026-02-28T10:00:12+00:00'));

    render(<StatusDashboard />);

    const banner = document.querySelector('.status-overall');
    expect(banner).toBeTruthy();
    expect(banner.classList.contains('overall-amber')).toBe(true);
    expect(screen.getByText('Partial Degradation')).toBeInTheDocument();

    // Test healthy variant
    const healthyData = { ...mockHealthData, overall_status: 'healthy' };
    mockUseQuery.mockReturnValue({ data: healthyData, isLoading: false, isError: false });
    const { container: c2 } = render(<StatusDashboard />);
    const banner2 = c2.querySelector('.status-overall');
    expect(banner2.classList.contains('overall-green')).toBe(true);
    expect(screen.getByText('All Systems Operational')).toBeInTheDocument();
  });
});
