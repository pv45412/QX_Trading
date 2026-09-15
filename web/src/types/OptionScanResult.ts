export interface VolatilityProfile {
  current_iv: number;
  forecast_rv: number;
  vol_edge: number;
  iv_percentile?: number;
}

export interface GEXProfile {
  gamma_flip: number;
  zero_gamma?: number;
  net_gex_dollars?: number;
  regime: 'LONG_GAMMA' | 'SHORT_GAMMA' | 'NEUTRAL';
}

export interface OptionProposal {
  symbol: string;
  contract_symbol: string;
  strategy: string;
  strike: number;
  expiration: string;
  option_type: 'CALL' | 'PUT';
  mid_price: number;
  multiplier: 100;
  max_risk: number;
  recommended_size_contracts: number;
  greeks: {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
  };
}

export interface OptionScanResult {
  symbol: string;
  underlying_price: number;
  volatility_result: VolatilityProfile;
  gex_profile?: GEXProfile;
  proposals: OptionProposal[];
  publication_state: 'VERIFIED' | 'SIMULATED' | 'BLOCKED';
}
