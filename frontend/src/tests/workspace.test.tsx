import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceProvider, useWorkspace } from '../app/WorkspaceContext';

const baseItems = [
  { symbol: '510300', name: '沪深300ETF', asset_class: '股票', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '511010', name: '国债ETF', asset_class: '债券', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '518880', name: '黄金ETF', asset_class: '黄金', market: 'SH', asset_type: 'etf', provider_symbol: null },
  { symbol: '511880', name: '货币ETF', asset_class: '现金', market: 'SH', asset_type: 'etf', provider_symbol: null },
] as const;
const addedItem = {
  symbol: '000001',
  name: '上证指数',
  asset_class: '股票',
  market: 'SH',
  asset_type: 'index',
  provider_symbol: 'sh000001',
} as const;

function response(items: readonly object[], current: string | null) {
  return new Response(JSON.stringify({
    ok: true,
    data: {
      items,
      current_symbol: current,
      comparison_symbols: items.map((item) => (item as { symbol: string }).symbol),
      updated_at: '2026-07-22T09:00:00+08:00',
    },
    meta: {
      source: 'local',
      as_of: '2026-07-22T09:00:00+08:00',
      request_id: 'workspace-test',
      is_fallback: false,
    },
    warnings: [],
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function Probe() {
  const workspace = useWorkspace();
  return (
    <div>
      <span data-testid="amount">{workspace.profile.amount_cny ?? '-'}</span>
      <span data-testid="watched">{workspace.watchedSymbols.length}</span>
      <span data-testid="risk">{workspace.riskSymbol ?? '-'}</span>
      <button
        onClick={() => void workspace.applyActions([
          { type: 'profile.patch', payload: { amount_cny: 100000, horizon_months: 24 } },
          { type: 'market.symbol.add', payload: { symbol: '000001' } },
          { type: 'risk.symbol.select', payload: { symbol: '000001' } },
        ])}
      >
        apply
      </button>
      <button onClick={() => void workspace.removeSymbol('000001')}>remove</button>
    </div>
  );
}

describe('WorkspaceProvider', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (init?.method === 'POST' && path.endsWith('/market/watchlist/items')) {
        return response([...baseItems, addedItem], '510300');
      }
      if (init?.method === 'POST' && path.endsWith('/market/watchlist/current')) {
        return response([...baseItems, addedItem], '000001');
      }
      if (init?.method === 'DELETE') {
        return response(baseItems, '510300');
      }
      return response(baseItems, '510300');
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('applies validated Agent actions to persisted profile and symbol state', async () => {
    render(<WorkspaceProvider><Probe /></WorkspaceProvider>);

    await waitFor(() => expect(screen.getByTestId('watched')).toHaveTextContent('4'));
    fireEvent.click(screen.getByText('apply'));
    expect(screen.getByTestId('amount')).toHaveTextContent('100000');
    await waitFor(() => expect(screen.getByTestId('watched')).toHaveTextContent('5'));
    expect(screen.getByTestId('risk')).toHaveTextContent('000001');

    fireEvent.click(screen.getByText('remove'));
    await waitFor(() => expect(screen.getByTestId('watched')).toHaveTextContent('4'));
    expect(screen.getByTestId('risk')).toHaveTextContent('510300');
  });
});
