import type { CatalogSymbol } from '../../api/types';

export function selectOverviewSymbols(
  representatives: CatalogSymbol[],
  watchedSymbols: CatalogSymbol[],
  selectedSymbols: string[],
  limit = 8,
): CatalogSymbol[] {
  const watchedBySymbol = new Map(watchedSymbols.map((item) => [item.symbol, item]));
  const focusSymbols = selectedSymbols.length > 0
    ? selectedSymbols
    : watchedSymbols.map((item) => item.symbol);
  const ordered = [
    ...focusSymbols.slice(0, 2).map((symbol) => watchedBySymbol.get(symbol)),
    ...representatives,
    ...watchedSymbols,
  ];
  const result: CatalogSymbol[] = [];
  const seen = new Set<string>();

  for (const item of ordered) {
    if (!item || seen.has(item.symbol)) continue;
    seen.add(item.symbol);
    result.push(item);
    if (result.length >= limit) break;
  }
  return result;
}
