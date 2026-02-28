import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import LotsTable from './components/LotsTable';
import Reconciliation from './components/Reconciliation';
import Settings from './components/Settings';
import Backtest from './components/Backtest';
import Orderblock from './components/Orderblock';
import Chart from './components/Chart';
import CombinedScore from './components/CombinedScore';
import BotDashboard from './components/BotDashboard';
import DecisionLog from './components/DecisionLog';
import Dashboard from './components/Dashboard';
import Overview from './components/Overview';
import SymbolLayout from './components/SymbolLayout';
import GlobalNav from './components/GlobalNav';
import StatusDashboard from './components/StatusDashboard';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { UserProvider } from './contexts/UserContext';
import FillNotification from './components/FillNotification';
import AlertBanner from './components/AlertBanner';
import { getServerIp } from './api/client';
import './App.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

/**
 * SymbolRedirect - Redirects old bookmark URLs to symbol-scoped routes.
 * Uses last-visited symbol from localStorage, falls back to BTCEUR.
 */
function SymbolRedirect({ subPath }) {
  const lastSymbol = localStorage.getItem('cashmgnt_last_symbol') || 'BTCEUR';
  return <Navigate to={`/s/${lastSymbol}/${subPath}`} replace />;
}

function AppContent() {
  // Server Public IP (fuer Binance Whitelisting)
  const { data: serverIpData } = useQuery({
    queryKey: ['server-ip'],
    queryFn: getServerIp,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return (
    <div className="App">
      <GlobalNav />
      <AlertBanner />

      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/s/:symbol" element={<SymbolLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="lots" element={<LotsTable />} />
          <Route path="chart" element={<Chart />} />
          <Route path="combined" element={<CombinedScore />} />
          <Route path="orderblock" element={<Orderblock />} />
          <Route path="bot" element={<BotDashboard />} />
          <Route path="bot/decisions" element={<DecisionLog />} />
          <Route path="reconciliation" element={<Reconciliation />} />
          <Route path="settings" element={<Settings />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="status" element={<StatusDashboard />} />
        </Route>
        {/* Redirect old bookmark URLs to symbol-scoped routes */}
        <Route path="/settings" element={<SymbolRedirect subPath="settings" />} />
        <Route path="/backtest" element={<SymbolRedirect subPath="backtest" />} />
        <Route path="/status" element={<SymbolRedirect subPath="status" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <FillNotification />

      <footer className="app-footer">
        <span>Cashflow Management v0.1.0</span>
        <a href="/docs" target="_blank" rel="noopener noreferrer" className="footer-link">API Docs</a>
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
          <UserProvider userId="user_123">
            <AppContent />
          </UserProvider>
        </WebSocketProvider>
      </QueryClientProvider>
    </BrowserRouter>
  );
}

export default App;
