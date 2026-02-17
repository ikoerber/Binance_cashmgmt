import { useState, memo } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import Dashboard from './components/Dashboard';
import LotsTable from './components/LotsTable';
import Reconciliation from './components/Reconciliation';
import Settings from './components/Settings';
import MacroSignal from './components/MacroSignal';
import Sentiment from './components/Sentiment';
import Orderblock from './components/Orderblock';
import { WebSocketProvider, useLivePrice } from './contexts/WebSocketContext';
import { getServerIp } from './api/client';
import './App.css';

// Memoize Komponenten, die nicht vom Preis abhaengen
const MemoReconciliation = memo(Reconciliation);
const MemoSettings = memo(Settings);
const MemoMacroSignal = memo(MacroSignal);
const MemoSentiment = memo(Sentiment);
const MemoOrderblock = memo(Orderblock);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function AppContent() {
  const [currentView, setCurrentView] = useState('dashboard');
  const userId = 'user_123';
  
  // Live BTC/EUR Preis
  const { price: marketPrice, loading: priceLoading, lastUpdate, source: priceSource, direction, changePct, isFlashing } = useLivePrice('BTCEUR', 10000);

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
          <h1>💰 BTC/EUR Cashflow Management</h1>
          <div className={`live-price ${isFlashing ? 'price-flash' : ''}`}>
            {priceLoading ? (
              <span className="price-loading">Lade Preis...</span>
            ) : (
              <>
                <span className="price-label">Live BTC/EUR:</span>
                <span className={`price-value ${direction === 'up' ? 'price-up' : direction === 'down' ? 'price-down' : ''}`}>
                  {direction === 'up' && '▲ '}
                  {direction === 'down' && '▼ '}
                  {marketPrice ? marketPrice.toLocaleString('de-DE', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  }) : '—'} €
                </span>
                {isFlashing && (
                  <span className={`price-alert ${direction === 'up' ? 'price-alert-up' : 'price-alert-down'}`}>
                    {changePct.toFixed(2)}%
                  </span>
                )}
                <span className="price-update">
                  {lastUpdate ? `(${lastUpdate.toLocaleTimeString('de-DE')})` : ''}
                </span>
                <span className={`ws-status ${priceSource === 'websocket' ? 'ws-connected' : 'ws-polling'}`}
                      title={priceSource === 'websocket' ? 'WebSocket verbunden' : 'REST Polling (Fallback)'}>
                  {priceSource === 'websocket' ? 'WS' : 'REST'}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="nav-links">
          <button 
            className={currentView === 'dashboard' ? 'active' : ''}
            onClick={() => setCurrentView('dashboard')}
          >
            📊 Dashboard
          </button>
          <button 
            className={currentView === 'lots' ? 'active' : ''}
            onClick={() => setCurrentView('lots')}
          >
            📋 TradeLots
          </button>
          <button
            className={currentView === 'macro' ? 'active' : ''}
            onClick={() => setCurrentView('macro')}
          >
            Makro-Signal
          </button>
          <button
            className={currentView === 'sentiment' ? 'active' : ''}
            onClick={() => setCurrentView('sentiment')}
          >
            Sentiment
          </button>
          <button
            className={currentView === 'orderblock' ? 'active' : ''}
            onClick={() => setCurrentView('orderblock')}
          >
            Orderblock
          </button>
          <button
            className={currentView === 'reconciliation' ? 'active' : ''}
            onClick={() => setCurrentView('reconciliation')}
          >
            Reconciliation
          </button>
          <button
            className={currentView === 'settings' ? 'active' : ''}
            onClick={() => setCurrentView('settings')}
          >
            Settings
          </button>
          <button
            onClick={() => window.open('http://localhost:8000/docs', '_blank')}
          >
            API Docs
          </button>
        </div>
      </nav>

      <div className="content">
        {currentView === 'dashboard' && (
          <Dashboard userId={userId} marketPrice={marketPrice || 50000} />
        )}
        {currentView === 'lots' && (
          <LotsTable userId={userId} marketPrice={marketPrice || 50000} />
        )}
        {currentView === 'macro' && (
          <MemoMacroSignal userId={userId} />
        )}
        {currentView === 'sentiment' && (
          <MemoSentiment userId={userId} />
        )}
        {currentView === 'orderblock' && (
          <MemoOrderblock userId={userId} marketPrice={marketPrice} />
        )}
        {currentView === 'reconciliation' && (
          <MemoReconciliation userId={userId} />
        )}
        {currentView === 'settings' && (
          <MemoSettings userId={userId} />
        )}
      </div>

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
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider userId="user_123">
        <AppContent />
      </WebSocketProvider>
    </QueryClientProvider>
  );
}

export default App;
