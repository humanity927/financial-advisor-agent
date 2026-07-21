import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { CatalogSymbol, ProfileInput, UiAction } from '../api/types';

const DEFAULT_WATCHLIST: CatalogSymbol[] = [
  { symbol: '510300', name: '沪深300ETF', asset_class: '股票', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '511010', name: '国债ETF', asset_class: '债券', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '518880', name: '黄金ETF', asset_class: '黄金', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '511880', name: '货币ETF', asset_class: '现金', market: 'SH', asset_type: 'etf', provider_symbol: null },
];

interface WorkspaceValue {
  profile: Partial<ProfileInput>;
  watchedSymbols: CatalogSymbol[];
  selectedSymbols: string[];
  riskSymbol: string | null;
  currentAllocationPct: Record<string, number> | null;
  patchProfile: (patch: Partial<ProfileInput>) => void;
  addSymbol: (symbol: CatalogSymbol) => boolean;
  removeSymbol: (symbol: string) => void;
  setSelectedSymbols: (symbols: string[]) => void;
  setRiskSymbol: (symbol: string | null) => void;
  setCurrentAllocationPct: (allocation: Record<string, number> | null) => void;
  applyActions: (actions: UiAction[]) => string[];
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Partial<ProfileInput>>({});
  const [watchedSymbols, setWatchedSymbols] = useState<CatalogSymbol[]>(DEFAULT_WATCHLIST);
  const [selectedSymbols, updateSelectedSymbols] = useState(DEFAULT_WATCHLIST.map((item) => item.symbol));
  const [riskSymbol, setRiskSymbol] = useState<string | null>(DEFAULT_WATCHLIST[0].symbol);
  const [currentAllocationPct, setCurrentAllocationPct] = useState<Record<string, number> | null>(null);

  const patchProfile = useCallback((patch: Partial<ProfileInput>) => {
    setProfile((current) => ({ ...current, ...patch }));
  }, []);

  const addSymbol = useCallback((symbol: CatalogSymbol) => {
    if (watchedSymbols.some((item) => item.symbol === symbol.symbol) || watchedSymbols.length >= 8) {
      return false;
    }
    setWatchedSymbols((current) => [...current, symbol]);
    updateSelectedSymbols((current) => [...current, symbol.symbol]);
    return true;
  }, [watchedSymbols]);

  const removeSymbol = useCallback((symbol: string) => {
    setWatchedSymbols((current) => current.filter((item) => item.symbol !== symbol));
    updateSelectedSymbols((current) => current.filter((item) => item !== symbol));
    setRiskSymbol((current) => (current === symbol ? null : current));
  }, []);

  const setSelectedSymbols = useCallback((symbols: string[]) => {
    setWatchedSymbols((watched) => {
      const allowed = new Set(watched.map((item) => item.symbol));
      updateSelectedSymbols(Array.from(new Set(symbols)).filter((symbol) => allowed.has(symbol)).slice(0, 8));
      return watched;
    });
  }, []);

  const applyActions = useCallback((actions: UiAction[]) => {
    const feedback: string[] = [];
    for (const action of actions) {
      switch (action.type) {
        case 'profile.patch':
          patchProfile(action.payload);
          feedback.push('已同步投资者画像到配置页');
          break;
        case 'market.symbol.add': {
          const existing = watchedSymbols.find((item) => item.symbol === action.payload.symbol);
          if (existing) {
            feedback.push(`${action.payload.symbol} 已在关注列表`);
          } else {
            const fallback: CatalogSymbol = {
              symbol: action.payload.symbol,
              name: action.payload.symbol,
              asset_class: '待核验',
              market: action.payload.symbol.startsWith('399') ? 'SZ' : 'SH',
              asset_type: action.payload.symbol.startsWith('0') || action.payload.symbol.startsWith('399') ? 'index' : 'etf',
              provider_symbol: null,
            };
            addSymbol(fallback);
            feedback.push(`已关注 ${action.payload.symbol}`);
          }
          break;
        }
        case 'market.symbol.remove':
          removeSymbol(action.payload.symbol);
          feedback.push(`已取消关注 ${action.payload.symbol}`);
          break;
        case 'risk.symbol.select':
          setRiskSymbol(action.payload.symbol);
          feedback.push(`风险分析已切换到 ${action.payload.symbol}`);
          break;
        case 'portfolio.inputs.patch':
          if (action.payload.profile) patchProfile(action.payload.profile);
          if (action.payload.current_allocation_pct) setCurrentAllocationPct(action.payload.current_allocation_pct);
          feedback.push('已同步配置输入');
          break;
        default:
          feedback.push('已拒绝未知界面动作');
      }
    }
    return Array.from(new Set(feedback));
  }, [addSymbol, patchProfile, removeSymbol, watchedSymbols]);

  const value = useMemo<WorkspaceValue>(() => ({
    profile,
    watchedSymbols,
    selectedSymbols,
    riskSymbol,
    currentAllocationPct,
    patchProfile,
    addSymbol,
    removeSymbol,
    setSelectedSymbols,
    setRiskSymbol,
    setCurrentAllocationPct,
    applyActions,
  }), [
    profile,
    watchedSymbols,
    selectedSymbols,
    riskSymbol,
    currentAllocationPct,
    patchProfile,
    addSymbol,
    removeSymbol,
    setSelectedSymbols,
    applyActions,
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
