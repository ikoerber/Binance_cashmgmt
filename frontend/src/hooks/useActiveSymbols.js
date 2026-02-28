import { useQuery } from '@tanstack/react-query';
import { getActiveSymbols } from '../api/client';
import { useUser } from '../contexts/UserContext';
import { getAllSymbols } from '../utils/symbolRegistry';

/**
 * Returns the list of symbols the user actually holds on Binance.
 * Falls back to all symbols on error or while loading.
 *
 * Refresh: 60s polling — balance changes are infrequent (fills, deposits).
 * The WebSocket balance_update event will invalidate this query for faster updates.
 */
export function useActiveSymbols() {
  const { userId } = useUser();

  const { data, isLoading, isError } = useQuery({
    queryKey: ['active-symbols', userId],
    queryFn: () => getActiveSymbols(userId),
    staleTime: 30_000,        // 30s stale — balance changes are rare
    refetchInterval: 60_000,  // 60s polling — low frequency, balance-driven
    retry: 2,
  });

  // While loading or on error: show all symbols (graceful degradation)
  const activeSymbols = data?.active_symbols || getAllSymbols();

  return { activeSymbols, isLoading, isError };
}
