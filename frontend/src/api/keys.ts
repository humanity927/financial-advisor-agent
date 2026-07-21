/** TanStack Query key 工厂 */
export const queryKeys = {
  health: ['health'] as const,
  marketSnapshot: (symbols: string[]) => ['market', 'snapshot', ...symbols] as const,
  marketCompare: (symbols: string[], range?: string) =>
    ['market', 'compare', range ?? 'default', ...symbols] as const,
  riskProfile: ['risk', 'profile'] as const,
  riskPortfolio: ['risk', 'portfolio'] as const,
  portfolioPlan: ['portfolio', 'plan'] as const,
  advisorReport: ['advisor', 'report'] as const,
};
