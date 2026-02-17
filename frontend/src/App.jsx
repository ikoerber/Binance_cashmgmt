import { memo } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import Dashboard from './components/Dashboard';
import LotsTable from './components/LotsTable';
import Reconciliation from './components/Reconciliation';
import Settings from './components/Settings';
import Orderblock from './components/Orderblock';
import CombinedScore from './components/CombinedScore';
import { WebSocketProvider, useLivePrice } from './contexts/WebSocketContext';
import { AppStateProvider } from './contexts/AppStateContext';
import FillNotification from './components/FillNotification';
import { getServerIp } from './api/client';
import './App.css';

// Memoize Komponenten, die nicht vom Preis abhaengen
const MemoReconciliation = memo(Reconciliation);
const MemoSettings = memo(Settings);
const MemoOrderblock = memo(Orderblock);
const MemoCombinedScore = memo(CombinedScore);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function AppContent() {
  const userId = 'user_123';

  // Live BTC/EUR Preis
  const { price: marketPrice, loading: priceLoading, lastUpdate, source, direction, changePct, isFlashing } = useLivePrice('BTCEUR', 10000);

  // Server Public IP (für Binance Whitelisting)
  const { data: serverIpData } = useQuery({
    queryKey: ['server-ip'],
    queryFn: getServerIp,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return (
    <div className="App">
      <nav className="navbar">
        <div className="navbar-content">
          <h1>BTC/EUR Cashflow Management</h1>
          <div className={`live-price ${isFlashing ? 'price-flash' : ''}`}>
            {priceLoading ? (
              <span className="price-loading">Lade Preis...</span>
            ) : (
              <>
                <span className="price-label">Live BTC/EUR:</span>
                <span className={`price-value ${direction === 'up' ? 'price-up' : direction === 'down' ? 'price-down' : ''}`}>
                  {direction === 'up' && '\u25B2 '}
                  {direction === 'down' && '\u25BC '}
                  {marketPrice ? marketPrice.toLocaleString('de-DE', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  }) : '\u2014'} \u20AC
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
        <div className="nav-links">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/lots">TradeLots</NavLink>
          <NavLink to="/combined">Combined Score</NavLink>
          <NavLink to="/orderblock">Orderblock</NavLink>
          <NavLink to="/reconciliation">Reconciliation</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <button onClick={() => window.open('http://localhost:8000/docs', '_blank')}>
            API Docs
          </button>
        </div>
      </nav>

      <AppStateProvider userId={userId} marketPrice={marketPrice || 50000}>
        <div className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/lots" element={<LotsTable />} />
            <Route path="/combined" element={<MemoCombinedScore />} />
            <Route path="/orderblock" element={<MemoOrderblock />} />
            <Route path="/reconciliation" element={<MemoReconciliation />} />
            <Route path="/settings" element={<MemoSettings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </AppStateProvider>

      <FillNotification />

      <footer className="app-footer">
        <span>BTC/EUR Cashflow Management v0.1.0</span>
        {serverIpData?.ip && (
          <span className="footer-ip">Server IP: {serverIpData.ip}</span>
        )}
      </footer>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider userId="user_123">
          <AppContent />
        </WebSocketProvider>
      </QueryClientProvider>
    </BrowserRouter>
  );
}

export default App;
