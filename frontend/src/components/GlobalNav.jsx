/**
 * GlobalNav - Tier-1 Navigation (immer sichtbar)
 *
 * Links: App-Name
 * Mitte: Symbol-Tabs (BTCEUR | ETHEUR | Overview)
 * Rechts: Settings-Link
 */
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { getAllSymbols, getPairLabel, isEurQuoted } from '../utils/symbolRegistry';

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
          <NavLink to="/backtest" className={({ isActive }) => `symbol-pill backtest-pill ${isActive ? 'active' : ''}`}>
            Backtest
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `symbol-pill settings-pill ${isActive ? 'active' : ''}`}>
            Settings
          </NavLink>
        </div>
      </div>
    </nav>
  );
};

export default GlobalNav;
