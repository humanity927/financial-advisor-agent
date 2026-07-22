import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import { ApiClientError, client } from '../api/client';
import type {
  CatalogSymbol,
  ProfileInput,
  UiAction,
  WatchlistData,
} from '../api/types';

export interface WorkspaceMutationResult {
  ok: boolean;
  code: string;
  message: string;
}

interface WorkspaceValue {
  profile: Partial<ProfileInput>;
  watchedSymbols: CatalogSymbol[];
  selectedSymbols: string[];
  riskSymbol: string | null;
  currentAllocationPct: Record<string, number> | null;
  watchlistLoading: boolean;
  watchlistError: string | null;
  patchProfile: (patch: Partial<ProfileInput>) => void;
  addSymbol: (symbol: CatalogSymbol | string) => Promise<WorkspaceMutationResult>;
  removeSymbol: (symbol: string) => Promise<WorkspaceMutationResult>;
  setSelectedSymbols: (symbols: string[]) => Promise<WorkspaceMutationResult>;
  setRiskSymbol: (symbol: string | null) => Promise<WorkspaceMutationResult>;
  setCurrentAllocationPct: (allocation: Record<string, number> | null) => void;
  applyActions: (actions: UiAction[]) => Promise<string[]>;
  refreshWatchlist: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

function mutationError(error: unknown): WorkspaceMutationResult {
  if (error instanceof ApiClientError) {
    return { ok: false, code: error.code, message: error.message };
  }
  return { ok: false, code: 'watchlist_unavailable', message: '关注列表服务暂不可用' };
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Partial<ProfileInput>>({});
  const [watchedSymbols, setWatchedSymbols] = useState<CatalogSymbol[]>([]);
  const [selectedSymbols, updateSelectedSymbols] = useState<string[]>([]);
  const [riskSymbol, updateRiskSymbol] = useState<string | null>(null);
  const [currentAllocationPct, setCurrentAllocationPct] =
    useState<Record<string, number> | null>(null);
  const [watchlistLoading, setWatchlistLoading] = useState(true);
  const [watchlistError, setWatchlistError] = useState<string | null>(null);

  const applyWatchlist = useCallback((state: WatchlistData) => {
    setWatchedSymbols(state.items);
    updateSelectedSymbols(state.comparison_symbols);
    updateRiskSymbol(state.current_symbol);
    setWatchlistError(null);
  }, []);

  const refreshWatchlist = useCallback(async () => {
    setWatchlistLoading(true);
    try {
      const response = await client.get<WatchlistData>('/market/watchlist');
      applyWatchlist(response.data);
    } catch (error) {
      setWatchlistError(mutationError(error).message);
    } finally {
      setWatchlistLoading(false);
    }
  }, [applyWatchlist]);

  useEffect(() => {
    void refreshWatchlist();
  }, [refreshWatchlist]);

  const patchProfile = useCallback((patch: Partial<ProfileInput>) => {
    setProfile((current) => ({ ...current, ...patch }));
  }, []);

  const addSymbol = useCallback(async (symbol: CatalogSymbol | string) => {
    const code = typeof symbol === 'string' ? symbol : symbol.symbol;
    try {
      const response = await client.post<WatchlistData>('/market/watchlist/items', {
        symbol: code,
      });
      applyWatchlist(response.data);
      const added = response.data.items.find((item) => item.symbol === code);
      return {
        ok: true,
        code: 'added',
        message: `已关注 ${code}${added ? ` · ${added.name}` : ''}`,
      };
    } catch (error) {
      return mutationError(error);
    }
  }, [applyWatchlist]);

  const removeSymbol = useCallback(async (symbol: string) => {
    try {
      const response = await client.delete<WatchlistData>(`/market/watchlist/items/${symbol}`);
      applyWatchlist(response.data);
      return { ok: true, code: 'removed', message: `已取消关注 ${symbol}` };
    } catch (error) {
      return mutationError(error);
    }
  }, [applyWatchlist]);

  const setSelectedSymbols = useCallback(async (symbols: string[]) => {
    try {
      const response = await client.post<WatchlistData>('/market/watchlist/comparison', {
        symbols,
      });
      applyWatchlist(response.data);
      return { ok: true, code: 'comparison_updated', message: '对比标的已更新' };
    } catch (error) {
      return mutationError(error);
    }
  }, [applyWatchlist]);

  const setRiskSymbol = useCallback(async (symbol: string | null) => {
    if (symbol === null) {
      updateRiskSymbol(null);
      return { ok: true, code: 'current_cleared', message: '已清除当前标的' };
    }
    try {
      const response = await client.post<WatchlistData>('/market/watchlist/current', { symbol });
      applyWatchlist(response.data);
      return { ok: true, code: 'current_updated', message: `当前标的已切换到 ${symbol}` };
    } catch (error) {
      return mutationError(error);
    }
  }, [applyWatchlist]);

  const applyActions = useCallback(async (actions: UiAction[]) => {
    const feedback: string[] = [];
    for (const action of actions) {
      switch (action.type) {
        case 'profile.patch':
          patchProfile(action.payload);
          feedback.push('已同步投资者画像到配置页');
          break;
        case 'market.symbol.add': {
          const result = await addSymbol(action.payload.symbol);
          feedback.push(
            result.code === 'duplicate_symbol'
              ? `${action.payload.symbol} 已在关注列表`
              : result.message,
          );
          break;
        }
        case 'market.symbol.remove': {
          const result = await removeSymbol(action.payload.symbol);
          feedback.push(result.message);
          break;
        }
        case 'risk.symbol.select': {
          const result = await setRiskSymbol(action.payload.symbol);
          feedback.push(result.message);
          break;
        }
        case 'portfolio.inputs.patch':
          if (action.payload.profile) patchProfile(action.payload.profile);
          if (action.payload.current_allocation_pct) {
            setCurrentAllocationPct(action.payload.current_allocation_pct);
          }
          feedback.push('已同步配置输入');
          break;
        default:
          feedback.push('已拒绝未知界面动作');
      }
    }
    return Array.from(new Set(feedback));
  }, [addSymbol, patchProfile, removeSymbol, setRiskSymbol]);

  const value = useMemo<WorkspaceValue>(() => ({
    profile,
    watchedSymbols,
    selectedSymbols,
    riskSymbol,
    currentAllocationPct,
    watchlistLoading,
    watchlistError,
    patchProfile,
    addSymbol,
    removeSymbol,
    setSelectedSymbols,
    setRiskSymbol,
    setCurrentAllocationPct,
    applyActions,
    refreshWatchlist,
  }), [
    profile,
    watchedSymbols,
    selectedSymbols,
    riskSymbol,
    currentAllocationPct,
    watchlistLoading,
    watchlistError,
    patchProfile,
    addSymbol,
    removeSymbol,
    setSelectedSymbols,
    setRiskSymbol,
    applyActions,
    refreshWatchlist,
  ]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

// Context hooks intentionally share this module with the provider boundary.
// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error('useWorkspace must be used within WorkspaceProvider');
  return context;
}
