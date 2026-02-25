/**
 * SymbolLayout - Wrapper fuer alle /s/:symbol/* Routes
 *
 * Liest :symbol aus URL, validiert gegen KNOWN_PAIRS,
 * stellt SymbolContext bereit (symbol + marketPrice),
 * rendert Tier-2 Sub-Navigation + <Outlet />.
 */
import { Outlet, NavLink, Navigate, useParams } from 'react-router-dom';
import { useLivePrice } from '../contexts/WebSocketContext';
import { SymbolProvider } from '../contexts/SymbolContext';
import { KNOWN_PAIRS, getPairLabel, getQuoteAsset, getQuoteDecimals, getQuoteLabel } from '../utils/symbolRegistry';

const SymbolLayout = () => {
  const { symbol } = useParams();

  // Live-Preis Hook — muss vor jeglichem Early Return aufgerufen werden (React Rules of Hooks)
  const { price: marketPrice, loading: priceLoading, lastUpdate, source, direction, changePct, isFlashing } = useLivePrice(symbol, 10000);

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
          </div>
          <div className="subnav-group">
            <span className="subnav-group-label">Admin</span>
            <NavLink to={`/s/${symbol}/reconciliation`}>Reconciliation</NavLink>
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
