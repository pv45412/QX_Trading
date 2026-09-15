export interface PositionItem {
  symbol: string;
  position_type: 'Long Shares' | 'Short Shares' | 'Long Call' | 'Long Put' | 'Bull Call Spread' | 'Bear Put Spread';
  entry_price: number;
  quantity: number;
  current_price?: number | null;
  target_price?: number | null;
  stop_loss?: number | null;
  cost_basis?: number;
  option_mark?: number | null;
}

export interface PortfolioBalance {
  total_equity: number;
  net_liquidation_value: number;
  buying_power: number;
  cash_balance: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  is_read_only: boolean;
  publication_state: 'VERIFIED' | 'SIMULATED' | 'BLOCKED';
}

export interface PositionResearchReport {
  symbol: string;
  position_type: string;
  current_price: number;
  entry_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  action_verdict: 'HOLD' | 'TRIM / TAKE PROFIT' | 'CLOSE / EXIT' | 'ROLL / ADJUST';
  confidence_score: number;
  verdict_summary: string;
  positive_factors: string[];
  negative_factors: string[];
  adjusted_stop_loss: number;
  adjusted_target_price: number;
  technical_metrics: Record<string, number | string | boolean>;
  risk_metrics: Record<string, number | string | boolean>;
  ai_evidence_summary?: string;
}
