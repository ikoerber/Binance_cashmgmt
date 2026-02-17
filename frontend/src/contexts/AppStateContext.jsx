import { createContext, useContext } from 'react';

const AppStateContext = createContext(null);

export function AppStateProvider({ userId, marketPrice, children }) {
  return (
    <AppStateContext.Provider value={{ userId, marketPrice }}>
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
