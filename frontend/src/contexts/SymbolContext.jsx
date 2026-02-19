import { createContext, useContext } from 'react';

const SymbolContext = createContext(null);

export function SymbolProvider({ symbol, marketPrice, children }) {
  return (
    <SymbolContext.Provider value={{ symbol, marketPrice }}>
      {children}
    </SymbolContext.Provider>
  );
}

export function useSymbol() {
  const ctx = useContext(SymbolContext);
  if (!ctx) {
    throw new Error('useSymbol must be used within SymbolProvider (are you on a /s/:symbol route?)');
  }
  return ctx;
}
