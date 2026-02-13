import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Dashboard from './components/Dashboard';
import LotsTable from './components/LotsTable';
import Reconciliation from './components/Reconciliation';
import Settings from './components/Settings';
import MacroSignal from './components/MacroSignal';
import { useLivePrice } from './hooks/useLivePrice';
import './App.css';

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
  const { price: marketPrice, loading: priceLoading, lastUpdate } = useLivePrice('BTCEUR', 10000);

  return (
    <div className="App">
      <nav className="navbar">
        <div className="navbar-content">
          <h1>💰 BTC/EUR Cashflow Management</h1>
          <div className="live-price">
            {priceLoading ? (
              <span className="price-loading">Lade Preis...</span>
            ) : (
              <>
                <span className="price-label">Live BTC/EUR:</span>
                <span className="price-value">
                  {marketPrice ? marketPrice.toLocaleString('de-DE', { 
                    minimumFractionDigits: 2, 
                    maximumFractionDigits: 2 
                  }) : '—'} €
                </span>
                <span className="price-update">
                  {lastUpdate ? `(${lastUpdate.toLocaleTimeString('de-DE')})` : ''}
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
          <MacroSignal userId={userId} />
        )}
        {currentView === 'reconciliation' && (
          <Reconciliation userId={userId} />
        )}
        {currentView === 'settings' && (
          <Settings userId={userId} />
        )}
      </div>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}

export default App;
