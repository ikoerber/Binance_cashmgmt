import { createContext, useContext, useState } from 'react';

const AppStateContext = createContext(null);

export function AppStateProvider({ userId, children }) {
  const [activeSymbol, setActiveSymbol] = useState('BTCEUR');
  const [marketPrice, setMarketPrice] = useState(50000);

  return (
    <AppStateContext.Provider value={{ userId, marketPrice, setMarketPrice, activeSymbol, setActiveSymbol }}>
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) {
    throw new Error('useAppState must be used within AppStateProvider');
  }
  return ctx;
}
