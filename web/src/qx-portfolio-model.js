export function buildPortfolioWorkspaceView(snapshot, evaluation = null) {
  if (!snapshot) return null;
  const risk = evaluation?.portfolio_risk ?? null;
  const lifecycleState = evaluation?.current_lifecycle_state ?? null;
  const attention = [...(Array.isArray(snapshot.reason_codes) ? snapshot.reason_codes : [])];
  if (risk?.state === 'PORTFOLIO_VETOED' || risk?.state === 'BLOCKED') {
    attention.push(...(Array.isArray(risk.reason_codes) ? risk.reason_codes : [risk.state]));
  }
  return {
    snapshot: {
      status: snapshot.status ?? 'UNAVAILABLE',
      publicationState: snapshot.publication_state ?? 'BLOCKED',
      pipelineVersion: snapshot.pipeline_version ?? null,
      readOnly: snapshot.read_only === true,
      accountId: snapshot.account_id ?? null,
      equity: finiteOrNull(snapshot.equity),
      cash: finiteOrNull(snapshot.cash),
      buyingPower: finiteOrNull(snapshot.buying_power),
      dailyRealizedPnl: finiteOrNull(snapshot.daily_realized_pnl),
      dailyUnrealizedPnl: finiteOrNull(snapshot.daily_unrealized_pnl),
      totalUnrealizedPnl: finiteOrNull(snapshot.total_unrealized_pnl),
      pnlStatus: snapshot.pnl_status ?? 'UNAVAILABLE',
      openOrdersCount: finiteOrNull(snapshot.open_orders_count),
      grossExposure: finiteOrNull(snapshot.gross_market_exposure),
      netExposure: finiteOrNull(snapshot.net_market_exposure),
      positions: Array.isArray(snapshot.positions) ? snapshot.positions.map(positionView) : [],
      greeks: snapshot.greeks ? greekView(snapshot.greeks) : null,
      greeksStatus: snapshot.greeks_status ?? 'UNAVAILABLE',
      sectors: Array.isArray(snapshot.sector_allocations) ? snapshot.sector_allocations.map(sectorView) : [],
      sectorStatus: snapshot.sector_status ?? 'UNAVAILABLE',
      sectorMappingSource: snapshot.sector_mapping_source ?? null,
      sectorMappingVersion: snapshot.sector_mapping_version ?? null,
      dataAsOf: snapshot.data_as_of ?? null,
      retrievedAt: snapshot.retrieved_at ?? null,
      freshness: snapshot.freshness ?? 'UNAVAILABLE',
      syncStatus: snapshot.sync_status ?? 'UNAVAILABLE',
      source: snapshot.source ?? null,
      providerLatencyMs: finiteOrNull(snapshot.provider_latency_ms),
      dependency: snapshot.dependency ?? null,
    },
    candidateImpact: risk ? {
      symbol: risk.symbol ?? evaluation?.symbol ?? null,
      lifecycleState,
      evaluationTimestamp: evaluation?.evaluation_timestamp ?? null,
      evaluationId: evaluation?.evaluation_id ?? null,
      state: risk.state ?? null,
      bindingConstraint: risk.binding_constraint ?? null,
      approvedContractsCap: finiteOrNull(risk.approved_contracts_cap),
      maxLossPerContract: finiteOrNull(risk.max_loss_per_contract),
      candidateTotalMaxLoss: finiteOrNull(risk.candidate_total_max_loss),
      buyingPowerRequired: finiteOrNull(risk.candidate_buying_power_required),
      symbolExposureBefore: finiteOrNull(risk.symbol_exposure_before),
      symbolExposureAfter: finiteOrNull(risk.symbol_exposure_after),
      sectorExposureBefore: finiteOrNull(risk.sector_exposure_before),
      sectorExposureAfter: finiteOrNull(risk.sector_exposure_after),
      portfolioDeltaBefore: finiteOrNull(risk.portfolio_delta_before),
      portfolioDeltaAfter: finiteOrNull(risk.portfolio_delta_after),
      portfolioGammaBefore: finiteOrNull(risk.portfolio_gamma_before),
      portfolioGammaAfter: finiteOrNull(risk.portfolio_gamma_after),
      portfolioThetaBefore: finiteOrNull(risk.portfolio_theta_before),
      portfolioThetaAfter: finiteOrNull(risk.portfolio_theta_after),
      portfolioVegaBefore: finiteOrNull(risk.portfolio_vega_before),
      portfolioVegaAfter: finiteOrNull(risk.portfolio_vega_after),
      reasonCodes: Array.isArray(risk.reason_codes) ? [...risk.reason_codes] : [],
      evidence: risk.evidence_ladder ?? null,
      dataAsOf: risk.data_as_of ?? null,
    } : null,
    attention: [...new Set(attention)],
  };
}

function positionView(position) {
  return {
    symbol: position.symbol ?? null,
    assetClass: position.asset_class ?? null,
    quantity: finiteOrNull(position.quantity),
    entryPrice: finiteOrNull(position.entry_price),
    currentPrice: finiteOrNull(position.current_price),
    marketValue: finiteOrNull(position.market_value),
    unrealizedPnl: finiteOrNull(position.unrealized_pnl),
    unrealizedPnlPct: finiteOrNull(position.unrealized_pnl_pct),
    concentrationPct: finiteOrNull(position.concentration_pct),
    sectorId: position.canonical_sector_id ?? null,
    providerSector: position.provider_sector_raw ?? null,
    sectorStatus: position.sector_status ?? 'UNAVAILABLE',
    sectorMappingSource: position.sector_mapping_source ?? null,
    sectorMappingVersion: position.sector_mapping_version ?? null,
    delta: finiteOrNull(position.delta),
    gamma: finiteOrNull(position.gamma),
    theta: finiteOrNull(position.theta),
    vega: finiteOrNull(position.vega),
    greeksStatus: position.greeks_status ?? 'UNAVAILABLE',
  };
}

function greekView(greeks) {
  return {
    delta: finiteOrNull(greeks.net_delta),
    gamma: finiteOrNull(greeks.net_gamma),
    theta: finiteOrNull(greeks.net_theta),
    vega: finiteOrNull(greeks.net_vega),
    betaWeightedDelta: finiteOrNull(greeks.beta_weighted_delta),
  };
}

function sectorView(sector) {
  return {
    sector: sector.sector ?? null,
    allocationPct: finiteOrNull(sector.allocation_pct),
    marketValue: finiteOrNull(sector.market_value),
    overconcentrated: sector.is_overconcentrated === true,
  };
}

function finiteOrNull(value) {
  if (value == null || typeof value === 'boolean' || (typeof value === 'string' && value.trim() === '')) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
