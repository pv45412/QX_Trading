export interface ETFMetrics {
  etf: string;
  sector: string;
  relative_5d: number | null;
  relative_20d: number | null;
  relative_60d: number | null;
  rs20_aligned: number | null;
  rs_momentum_5d: number | null;
  rs_quadrant: 'LEADING' | 'WEAKENING' | 'LAGGING' | 'IMPROVING' | null;
  rs_status: string | null;
}

export interface StockMover {
  symbol: string;
  price: number;
  change_pct: number;
  volume: number;
  rvol: number;
}

export interface MarketSnapshot {
  snapshot_id?: string;
  timestamp: string;
  etf_rows: ETFMetrics[];
  movers?: StockMover[];
  age_status?: 'RECENT' | 'OLD' | 'UNKNOWN';
  age_seconds?: number | null;
}
