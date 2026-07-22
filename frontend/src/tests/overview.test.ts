import { describe, expect, it } from 'vitest';
import type { CatalogSymbol } from '../api/types';
import { selectOverviewSymbols } from '../features/overview/snapshotSelection';

const item = (symbol: string, name: string, assetType: 'etf' | 'index' = 'index'): CatalogSymbol => ({
  symbol,
  name,
  asset_class: assetType === 'etf' ? '债券' : '股票',
  market: 'SH',
  asset_type: assetType,
  provider_symbol: null,
});

describe('overview snapshot selection', () => {
  it('prioritizes at most two selected watchlist items and fills directory representatives', () => {
    const representatives = [item('000001', '上证指数'), item('000300', '沪深300指数')];
    const watched = [item('511010', '国债ETF', 'etf'), item('518880', '黄金ETF', 'etf')];

    expect(selectOverviewSymbols(representatives, watched, ['518880', '511010']))
      .toEqual([watched[1], watched[0], representatives[0], representatives[1]]);
  });

  it('deduplicates catalog and watchlist entries', () => {
    const shared = item('000300', '沪深300指数');
    expect(selectOverviewSymbols([shared], [shared], ['000300'])).toEqual([shared]);
  });
});
