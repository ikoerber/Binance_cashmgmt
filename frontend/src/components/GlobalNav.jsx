/**
 * GlobalNav - Tier-1 Navigation (immer sichtbar)
 *
 * Links: App-Name
 * Mitte: Symbol-Tabs (BTCEUR | ETHEUR | Overview)
 * Rechts: Status Dot (health indicator) linking to /status
 */
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getAllSymbols, getPairLabel, isEurQuoted } from '../utils/symbolRegistry';
import { getHealth } from '../api/client';

/**
 * Beim Symbol-Wechsel: Sub-Page beibehalten.
 * /s/BTCEUR/lots → Klick ETHEUR → /s/ETHEUR/lots
 */
function buildSymbolUrl(newSymbol, currentPathname) {
  const match = currentPathname.match(/^\/s\/[^/]+(\/.*)?$/);
  const subPath = match?.[1] || '';
  return `/s/${newSymbol}${subPath}`;
}

const GlobalNav = () => {
  const location = useLocation();
  const navigate = useNavigate();

  // Aktuelles Symbol aus URL extrahieren (falls auf /s/:symbol Route)
  const symbolMatch = location.pathname.match(/^\/s\/([^/]+)/);
  const currentSymbol = symbolMatch?.[1] || null;

  const handleSymbolClick = (sym) => {
    navigate(buildSymbolUrl(sym, location.pathname));
  };

  // Health status for status dot
  const userId = 'user_123';
  const { data: health, isLoading: healthLoading, isError: healthError } = useQuery({
    queryKey: ['health', userId],
    queryFn: () => getHealth(userId),
    refetchInterval: 15_000,  // 15s — longer than StatusDashboard (10s) to reduce polling when dashboard not open
    staleTime: 10_000,        // Shares cache with StatusDashboard's useQuery (same queryKey)
  });

  const overallColor = health?.overall_status
    ? { healthy: 'green', degraded: 'amber', critical: 'red' }[health.overall_status] || 'amber'
    : null;

  return (
    <nav className="navbar">
      <div className="navbar-content">
        <h1>
          <NavLink to="/" style={{ color: 'inherit', textDecoration: 'none' }}>
            Cashflow Management
          </NavLink>
        </h1>
        <div className="symbol-selector">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `symbol-pill ${isActive ? 'active' : ''}`}
          >
            Overview
          </NavLink>
          {getAllSymbols().map(sym => (
            <button
              key={sym}
              className={`symbol-pill ${sym === currentSymbol ? 'active' : ''} ${!isEurQuoted(sym) ? 'btc-quoted' : ''}`}
              onClick={() => handleSymbolClick(sym)}
            >
              {getPairLabel(sym)}
            </button>
          ))}
        </div>
        <div className="global-nav-right">
          {healthLoading && !health && (
            <NavLink to="/status" className="status-dot-link" title="System Status">
              <span className="status-dot dot-loading" />
            </NavLink>
          )}
          {!healthError && overallColor && (
            <NavLink to="/status" className="status-dot-link" title={`System: ${health.overall_status}`}>
              <span className={`status-dot dot-${overallColor}`} />
            </NavLink>
          )}
        </div>
      </div>
    </nav>
  );
};

export default GlobalNav;
