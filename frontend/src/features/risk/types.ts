import type { ApiResponse } from '../../api/types';

export interface RiskDimension {
  dimension: string;
  score: number;
  max_score: number;
}

export interface RiskProfileData {
  score: number;
  risk_level: string;
  score_breakdown: Record<string, number>;
  hard_limits: string[];
  dimensions: RiskDimension[];
}

export interface AssetRiskMetrics {
  observation_count: number;
  start_date: string;
  end_date: string;
  annual_return_pct: number;
  annual_volatility_pct: number;
  max_drawdown_pct: number;
  daily_var_95_pct: number;
  daily_cvar_95_pct: number;
}

export interface AssetRiskResult {
  symbol: string;
  name: string;
  asset_class: string;
  metrics: AssetRiskMetrics | null;
  source: string | null;
  warning: string | null;
  error?: string;
}

export interface AssetRiskData {
  assets: AssetRiskResult[];
  method: string;
}

export interface CurvePoint {
  date: string;
  value: number;
}

export interface CorrelationMatrix {
  symbols: string[];
  values: Array<Array<number | null>>;
}

export interface PortfolioMetrics {
  observation_count: number;
  start_date: string;
  end_date: string;
  annual_return_pct: number;
  annual_volatility_pct: number;
  max_drawdown_pct: number;
  daily_var_95_pct: number;
  daily_cvar_95_pct: number;
}

export interface PortfolioAnalysis {
  weights_pct: Record<string, number>;
  portfolio_metrics: PortfolioMetrics;
  correlation_matrix: CorrelationMatrix;
  net_value_curve: CurvePoint[];
  drawdown_curve: CurvePoint[];
  methodology: Record<string, string>;
}

export interface PortfolioAsset {
  symbol: string;
  name: string;
  asset_class: string;
  weight_pct: number;
  source: string;
  warning: string | null;
}

export interface PortfolioRiskData {
  portfolio: PortfolioAnalysis | null;
  assets: PortfolioAsset[];
  method: string;
}

export type RiskProfileResponse = ApiResponse<RiskProfileData>;
export type AssetRiskResponse = ApiResponse<AssetRiskData>;
export type PortfolioRiskResponse = ApiResponse<PortfolioRiskData>;
