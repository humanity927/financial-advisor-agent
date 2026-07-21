import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WorkspaceProvider, useWorkspace } from '../app/WorkspaceContext';

function Probe() {
  const workspace = useWorkspace();
  return (
    <div>
      <span data-testid="amount">{workspace.profile.amount_cny ?? '-'}</span>
      <span data-testid="watched">{workspace.watchedSymbols.length}</span>
      <span data-testid="risk">{workspace.riskSymbol ?? '-'}</span>
      <button
        onClick={() => workspace.applyActions([
          { type: 'profile.patch', payload: { amount_cny: 100000, horizon_months: 24 } },
          { type: 'market.symbol.add', payload: { symbol: '000001' } },
          { type: 'risk.symbol.select', payload: { symbol: '000001' } },
        ])}
      >
        apply
      </button>
      <button onClick={() => workspace.removeSymbol('000001')}>remove</button>
    </div>
  );
}

describe('WorkspaceProvider', () => {
  it('applies validated Agent actions to shared profile and symbol state', () => {
    render(<WorkspaceProvider><Probe /></WorkspaceProvider>);

    fireEvent.click(screen.getByText('apply'));
    expect(screen.getByTestId('amount')).toHaveTextContent('100000');
    expect(screen.getByTestId('watched')).toHaveTextContent('5');
    expect(screen.getByTestId('risk')).toHaveTextContent('000001');

    fireEvent.click(screen.getByText('remove'));
    expect(screen.getByTestId('watched')).toHaveTextContent('4');
    expect(screen.getByTestId('risk')).toHaveTextContent('-');
  });
});
