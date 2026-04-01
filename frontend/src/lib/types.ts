// ═══════════════════════════════════════════════════════════════
//  TradeSignal India v2 — Type Definitions
// ═══════════════════════════════════════════════════════════════

export interface Stock {
  id: number;
  ticker: string;
  name: string;
  sector: string;
  cap: 'Large' | 'Mid' | 'Small';
  is_active: boolean;
}

export interface EntryExit {
  action: string;
  entry_price: number | null;
  target_price: number | null;
  stop_loss: number | null;
  risk_reward: number;
  potential_profit_pct: number;
  potential_loss_pct: number;
}

export interface IndicatorScore {
  score: number;
  max: number;
  reason: string;
}

export interface NewsSentiment {
  sentiment: string;
  score: number;
  impact: string;
  source: string;
  article_count: number;
}

export interface AIData {
  ai_analysis: string;
  ai_confidence_modifier: number;
  ai_recommendation?: string;
  ai_key_factors?: string[];
  ai_risk_factors?: string[];
  ai_expected_move?: number;
  source: string;
}

export interface ScanResult {
  ticker: string;
  name: string;
  sector: string;
  cap: string;
  current_price: number;
  final_confidence: number;
  final_signal: string;
  base_confidence: number;
  news_modifier: number;
  ai_modifier: number;
  entry_exit: EntryExit;
  sr_levels: {
    supports: number[];
    resistances: number[];
    pivot: number;
    r1?: number; r2?: number; r3?: number;
    s1?: number; s2?: number; s3?: number;
  };
  indicator_scores: Record<string, IndicatorScore>;
  news_sentiment: NewsSentiment;
  ai_data: AIData;
  holding_mode: string;
  technical_details: Record<string, any>;
}

export interface ScanSummary {
  scan_id: string;
  scan_date: string;
  mode: string;
  scope: string;
  total_stocks: number;
  analyzed: number;
  errors: number;
  buy_signals_count: number;
  news_articles_fetched: number;
}

export interface Allocation {
  ticker: string;
  name: string;
  price: number;
  confidence: number;
  allocation_pct: number;
  amount: number;
  shares: number;
  target: number | null;
  stop_loss: number | null;
}

export interface Trade {
  id: number;
  stock_ticker: string;
  stock_name: string;
  status: 'OPEN' | 'PARTIAL_EXIT' | 'CLOSED';
  entry_price: number;
  entry_date: string;
  shares_bought: number;
  shares_remaining: number | null;
  current_target: number | null;
  current_stop_loss: number | null;
  exit_price: number | null;
  exit_date: string | null;
  exit_reason: string | null;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  holding_mode: string;
}

export interface NewsArticle {
  title: string;
  summary: string;
  link: string;
  published: string;
  source: string;
  impact_level?: string;
  match_type?: string;
}

export interface ScanRequest {
  scope: string;
  sectors: string[];
  mode: string;
  use_ai: boolean;
  min_confidence: number;
  max_positions: number;
  capital: number;
}

export type SignalType = 'STRONG BUY' | 'BUY' | 'HOLD / NEUTRAL' | 'SELL' | 'STRONG SELL';
