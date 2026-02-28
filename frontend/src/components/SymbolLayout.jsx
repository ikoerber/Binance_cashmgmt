/**
 * SymbolLayout - Wrapper fuer alle /s/:symbol/* Routes
 *
 * Liest :symbol aus URL, validiert gegen KNOWN_PAIRS,
 * stellt SymbolContext bereit (symbol + marketPrice),
 * rendert Tier-2 Sub-Navigation + <Outlet />.
 */
import { Outlet, NavLink, Navigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useLivePrice } from '../contexts/WebSocketContext';
import { SymbolProvider } from '../contexts/SymbolContext';
import { getDryRunStatus } from '../api/client';
import { KNOWN_PAIRS, getPairLabel, getQuoteAsset, getQuoteDecimals, getQuoteLabel } from '../utils/symbolRegistry';

const SymbolLayout = () => {
  const { symbol } = useParams();

  // Live-Preis Hook — muss vor jeglichem Early Return aufgerufen werden (React Rules of Hooks)
  const { price: marketPrice, loading: priceLoading, lastUpdate, source, direction, changePct, isFlashing } = useLivePrice(symbol, 10000);

  // Dry-run status for nav badge
  const userId = 'user_123';
  const { data: dryRunStatus } = useQuery({
    queryKey: ['dry-run-status', userId],
    queryFn: () => getDryRunStatus(userId),
    refetchInterval: 15000,
    staleTime: 10000,
  });
  const isDryRunActive = dryRunStatus?.is_active ?? false;

  // Validierung: unbekanntes Symbol → redirect
  if (!KNOWN_PAIRS[symbol]) {
    return <Navigate to="/s/BTCEUR" replace />;
  }

  return (
    <SymbolProvider symbol={symbol} marketPrice={marketPrice || 0}>
      {/* Tier-2: Sub-Navigation + Live-Preis */}
      <div className="symbol-subnav">
        <div className="subnav-links">
          <div className="subnav-group">
            <span className="subnav-group-label">Trading</span>
            <NavLink to={`/s/${symbol}/dashboard`}>Dashboard</NavLink>
            <NavLink to={`/s/${symbol}/lots`}>TradeLots</NavLink>
          </div>
          <div className="subnav-group">
            <span className="subnav-group-label">Analyse</span>
            <NavLink to={`/s/${symbol}/combined`}>Combined Score</NavLink>
            <NavLink to={`/s/${symbol}/orderblock`}>Orderblocks</NavLink>
            <NavLink to="/backtest">Backtest</NavLink>
          </div>
          <div className="subnav-group">
            <span className="subnav-group-label">Bot</span>
            <NavLink to={`/s/${symbol}/bot`} className="bot-nav-link">
              Bot Dashboard
              {isDryRunActive && <span className="bot-nav-badge" />}
            </NavLink>
            <NavLink to={`/s/${symbol}/bot/decisions`}>Decision Log</NavLink>
          </div>
          <div className="subnav-group">
            <span className="subnav-group-label">Admin</span>
            <NavLink to={`/s/${symbol}/reconciliation`}>Reconciliation</NavLink>
            <NavLink to="/settings">Settings</NavLink>
            <NavLink to="/status">Status</NavLink>
            <a href="/docs" target="_blank" rel="noopener noreferrer">API Docs</a>
          </div>
        </div>
        <div className={`live-price ${isFlashing ? 'price-flash' : ''}`}>
          {priceLoading ? (
            <span className="price-loading">Lade Preis...</span>
          ) : (
            <>
              <span className="price-label">Live {getPairLabel(symbol)}:</span>
              <span className={`price-value ${direction === 'up' ? 'price-up' : direction === 'down' ? 'price-down' : ''}`}>
                {direction === 'up' && '\u25B2 '}
                {direction === 'down' && '\u25BC '}
                {marketPrice ? marketPrice.toLocaleString('de-DE', {
                  minimumFractionDigits: getQuoteDecimals(symbol),
                  maximumFractionDigits: getQuoteDecimals(symbol)
                }) : '\u2014'} {getQuoteAsset(symbol) === 'EUR' ? '\u20ac' : getQuoteLabel(symbol)}
              </span>
              {isFlashing && (
                <span className={`price-alert ${direction === 'up' ? 'price-alert-up' : 'price-alert-down'}`}>
                  {changePct.toFixed(2)}%
                </span>
              )}
              <span className="price-update">
                {lastUpdate ? `(${lastUpdate.toLocaleTimeString('de-DE')})` : ''}
              </span>
              <span className={`ws-status ${source === 'websocket' ? 'ws-connected' : 'ws-polling'}`}
                    title={source === 'websocket' ? 'WebSocket verbunden' : 'REST Polling (Fallback)'}>
                {source === 'websocket' ? 'WS' : 'REST'}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Child Routes */}
      <div className="content">
        <Outlet />
      </div>
    </SymbolProvider>
  );
};

export default SymbolLayout;
