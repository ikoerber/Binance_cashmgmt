/**
 * GlobalNav.test.jsx
 *
 * Tests for the status dot in GlobalNav:
 * - DASH-04: Status dot color reflects overall system health
 * - DASH-04: Status dot links to /status
 * - Loading and error states
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// Mock useQuery from TanStack Query
const mockUseQuery = vi.fn();
vi.mock('@tanstack/react-query', () => ({
  useQuery: (...args) => mockUseQuery(...args),
}));

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  NavLink: ({ to, children, className, ...props }) => {
    const cls = typeof className === 'function' ? className({ isActive: false }) : className;
    return <a href={to} className={cls} {...props}>{children}</a>;
  },
  useLocation: () => ({ pathname: '/' }),
  useNavigate: () => vi.fn(),
}));

// Mock symbolRegistry
vi.mock('../../utils/symbolRegistry', () => ({
  getAllSymbols: () => ['BTCEUR'],
  getPairLabel: (s) => s,
  isEurQuoted: () => true,
}));

import GlobalNav from '../GlobalNav';

const healthyData = { overall_status: 'healthy', services: {}, checked_at: '2026-02-28T10:00:00Z' };
const degradedData = { overall_status: 'degraded', services: {}, checked_at: '2026-02-28T10:00:00Z' };
const criticalData = { overall_status: 'critical', services: {}, checked_at: '2026-02-28T10:00:00Z' };

describe('GlobalNav Status Dot', () => {
  // Test 1 (DASH-04): Status dot renders with green class when healthy
  it('renders status dot with green class when overall_status is healthy', () => {
    mockUseQuery.mockReturnValue({ data: healthyData, isLoading: false, isError: false });

    render(<GlobalNav />);

    const dot = document.querySelector('.status-dot.dot-green');
    expect(dot).toBeTruthy();
  });

  // Test 2 (DASH-04): Status dot renders with amber class when degraded
  it('renders status dot with amber class when overall_status is degraded', () => {
    mockUseQuery.mockReturnValue({ data: degradedData, isLoading: false, isError: false });

    render(<GlobalNav />);

    const dot = document.querySelector('.status-dot.dot-amber');
    expect(dot).toBeTruthy();
  });

  // Test 3 (DASH-04): Status dot renders with red class when critical
  it('renders status dot with red class when overall_status is critical', () => {
    mockUseQuery.mockReturnValue({ data: criticalData, isLoading: false, isError: false });

    render(<GlobalNav />);

    const dot = document.querySelector('.status-dot.dot-red');
    expect(dot).toBeTruthy();
  });

  // Test 4 (DASH-04): Status dot links to /status route
  it('links status dot to /status', () => {
    mockUseQuery.mockReturnValue({ data: healthyData, isLoading: false, isError: false });

    render(<GlobalNav />);

    const link = document.querySelector('.status-dot-link');
    expect(link).toBeTruthy();
    expect(link.getAttribute('href')).toBe('/status');
  });

  // Test 5: Loading state shows pulsing gray dot
  it('shows loading dot when health data is loading', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true, isError: false });

    render(<GlobalNav />);

    const dot = document.querySelector('.status-dot.dot-loading');
    expect(dot).toBeTruthy();
  });

  // Test 6: Error state hides dot entirely
  it('hides status dot when health fetch fails', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isError: true });

    render(<GlobalNav />);

    const dot = document.querySelector('.status-dot');
    expect(dot).toBeNull();
  });
});
