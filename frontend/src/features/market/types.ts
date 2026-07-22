import type { MarketSnapshot } from '../../api/types';

export type MarketRange = '1M' | '3M' | '1Y';
export type MarketReturnWindow = '20d' | '60d' | '252d';

export interface MarketSymbolSummary {
  symbol: string;
  name: string;
  asset_class: string;
}

export interface MarketComparePoint {
  date: string;
  close: number;
  normalized: number;
}

export interface MarketNormalizedSeries extends MarketSymbolSummary {
  points: MarketComparePoint[];
}

export interface MarketIntervalReturn extends MarketSymbolSummary {
  returns: Record<MarketReturnWindow, number | null>;
}

export interface MarketSourceDetail {
  symbol: string;
  name: string;
  source: MarketSnapshot['source'];
  provider: MarketSnapshot['provider'];
  origin_source: MarketSnapshot['origin_source'];
  fetched_at: string;
  latest_trade_date: string | null;
  cache_status: MarketSnapshot['cache_status'];
  stale: boolean;
  is_fallback: boolean;
  warning: string | null;
}

export interface MarketCompareData {
  symbols: MarketSymbolSummary[];
  range_days: number;
  common_start_date: string | null;
  latest_trade_date: string | null;
  observation_count: number;
  normalized_series: MarketNormalizedSeries[];
  interval_returns: MarketIntervalReturn[];
  snapshots: MarketSnapshot[];
  source_details: MarketSourceDetail[];
  method: string;
  warnings: string[];
}
