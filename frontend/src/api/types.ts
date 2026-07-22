/** 冻结契约 — 与第 6 节 API 结构对齐 */

export interface ApiMeta {
  source: 'akshare' | 'tushare' | 'cache' | 'fixture' | 'system' | 'local' | 'mixed';
  as_of: string;
  request_id: string;
  is_fallback: boolean;
}

export interface ApiError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface ApiResponse<T> {
  ok: boolean;
  data: T;
  meta: ApiMeta;
  warnings: string[];
  error?: ApiError;
}

/** 市场行情 */
export interface MarketSnapshot {
  symbol: string;
  name: string;
  asset_class: string;
  latest_price: number;
  previous_close: number;
  daily_change_pct: number;
  trade_date: string;
  source: string;
  provider: 'akshare' | 'tushare' | 'fixture' | null;
  origin_source: string | null;
  is_fallback: boolean;
  warning: string | null;
  fetched_at: string;
  latest_trade_date: string | null;
  cache_status: 'not_used' | 'fresh' | 'stale';
  stale: boolean;
  cached_at: string | null;
  is_stale: boolean;
}

/** 投资者画像 */
export interface ScoreBreakdown {
  [key: string]: number;
}

export interface RiskAssessment {
  score: number;
  risk_level: string;
  score_breakdown: ScoreBreakdown;
  hard_limits: string[];
}

/** 资产配置 */
export interface AllocationResult {
  risk_score: number;
  scored_risk_level: string;
  effective_risk_level: string;
  score_breakdown: ScoreBreakdown;
  constraints_applied: string[];
  allocation_pct: Record<string, number>;
  allocation_amount_cny: Record<string, number>;
  total_amount_cny: number;
  method: string;
}

export interface PortfolioPlanResult extends AllocationResult {
  adjustment_steps: string[];
  rationale: string[];
  current_allocation_pct: Record<string, number> | null;
  current_allocation_amount_cny: Record<string, number> | null;
  allocation_deviation_pct: Record<string, number> | null;
  allocation_deviation_amount_cny: Record<string, number> | null;
}

/** 画像表单输入 */
export interface ProfileInput {
  amount_cny: number;
  horizon_months: number;
  max_loss_pct: number;
  income_stability: 'unstable' | 'stable' | 'very_stable';
  experience: 'none' | 'basic' | 'regular' | 'expert';
  liquidity_need: 'high' | 'medium' | 'low';
  emergency_fund_months: number;
}

/** 系统健康 */
export interface HealthStatus {
  status: string;
  akshare_installed: boolean;
  tushare_configured: boolean;
  provider_priority: string[];
  cache_directory: string;
  cache_writable: boolean;
  fixture_path: string;
  fixture_available: boolean;
  force_fixture: boolean;
  supported_symbol_count: number;
}

export interface CatalogSymbol {
  symbol: string;
  name: string;
  asset_class: string;
  market: 'SH' | 'SZ';
  asset_type: 'etf' | 'index';
  provider_symbol: string | null;
}

export interface CatalogSearchData {
  items: CatalogSymbol[];
  catalog_fetched_at: string | null;
  query: string;
  selection_note?: string | null;
}

export interface WatchlistData {
  items: CatalogSymbol[];
  current_symbol: string | null;
  comparison_symbols: string[];
  updated_at: string;
}

export type ProfilePatch = Partial<ProfileInput>;

export type UiAction =
  | { type: 'profile.patch'; payload: ProfilePatch }
  | { type: 'market.symbol.add'; payload: { symbol: string } }
  | { type: 'market.symbol.remove'; payload: { symbol: string } }
  | { type: 'risk.symbol.select'; payload: { symbol: string } }
  | {
      type: 'portfolio.inputs.patch';
      payload: {
        profile?: ProfilePatch | null;
        current_allocation_pct?: Record<string, number> | null;
      };
    };

export interface ChatToolCall {
  tool: string;
  called_at: string;
  ok: boolean;
  source: string;
  as_of: string | null;
  is_fallback: boolean;
  error_code: string | null;
  summary: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  status: 'complete' | 'error' | 'cancelled';
  context_status: 'current' | 'historical';
  source: string;
  as_of: string | null;
  is_fallback: boolean;
  tool_calls: ChatToolCall[];
  actions: UiAction[];
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  profile: ProfilePatch;
  symbols: string[];
  risk_symbol: string | null;
  current_allocation_pct: Record<string, number> | null;
  personalization_active: boolean;
  messages: ChatMessage[];
}

export interface AdvisorRunStatus {
  request_id: string;
  active: boolean;
  tool_calls: ChatToolCall[];
}

export interface ChatTurnData {
  session: ChatSession;
  message: ChatMessage;
  missing_fields: string[];
  actions: UiAction[];
}

export interface SessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  symbols: string[];
  profile_fields: number;
}
