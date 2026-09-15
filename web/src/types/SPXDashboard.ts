export interface SPXPriceData {
  symbol: string;
  spx_close: number;
  change: number;
  change_pct: number;
  timestamp: string;
}

export interface GEXFlipData {
  gamma_flip: number;
  vwap: number;
  vwap_upper1: number;
  vwap_lower1: number;
  orb_15m_high: number;
  orb_15m_low: number;
}

export interface SPXDashboardState {
  spxData: SPXPriceData | null;
  gexData: GEXFlipData | null;
  quality_score?: number;
  is_loading: boolean;
  error?: string | null;
}
