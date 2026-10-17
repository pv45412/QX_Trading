import React from 'react';
import {Activity, AlertTriangle, CheckCircle2, Minus, TrendingDown, TrendingUp, Zap} from 'lucide-react';

/**
 * QXMarketDriverPanel
 *
 * Renders the backend market_driver result from the canonical v2 evaluation.
 * Accepts the raw `market_driver` object from the API payload (already extracted
 * by qx-v2-adapter as `canonical.marketDriver`).
 *
 * Props:
 *   driver   — the market_driver object from the v2 payload, or null
 *   symbol   — the symbol this driver applies to (for labelling)
 *   compact  — if true, renders a compact single-line form (for Today sidebar)
 *   blockedReason — if the pipeline is BLOCKED, the specific reason code
 */
export default function QXMarketDriverPanel({driver, symbol, compact = false, blockedReason = null}) {
  if (!driver) {
    return <DriverUnavailable symbol={symbol} compact={compact} blockedReason={blockedReason}/>;
  }

  const status = driver.status ?? 'UNAVAILABLE';

  if (status === 'UNAVAILABLE' || status === 'BLOCKED' || status === 'INSUFFICIENT') {
    const reasons = Array.isArray(driver.reason_codes) ? driver.reason_codes : [];
    return <DriverUnavailable symbol={symbol} compact={compact} blockedReason={blockedReason} driverReasons={reasons} status={status}/>;
  }

  const primary = driver.primary_driver ?? null;
  const secondaries = Array.isArray(driver.secondary_drivers) ? driver.secondary_drivers : [];
  const confirming = Array.isArray(driver.confirming_evidence) ? driver.confirming_evidence : [];
  const conflicting = Array.isArray(driver.conflicting_evidence) ? driver.conflicting_evidence : [];
  const coverage = driver.coverage ?? null;

  if (compact) {
    return <CompactDriver primary={primary} status={status} coverage={coverage}/>;
  }

  return (
    <div className="qx-driver-panel" data-status={status}>
      <div className="qx-driver-header">
        <div className="qx-driver-status-row">
          <span className={`qx-driver-status-badge qx-driver-status-${status.toLowerCase()}`}>{status}</span>
          {coverage && (
            <span className="qx-driver-coverage">
              {coverage.observed_sources}/{coverage.required_sources} sources
            </span>
          )}
        </div>
        {driver.data_as_of && <small className="qx-driver-timestamp">As of {shortTime(driver.data_as_of)}</small>}
      </div>

      {primary ? (
        <div className="qx-driver-primary">
          <div className="qx-driver-archetype">
            <StrengthIcon strength={primary.strength} direction={primary.direction}/>
            <div>
              <strong className="qx-driver-archetype-id">{formatArchetype(primary.driver_id)}</strong>
              <p className="qx-driver-archetype-label">{primary.label}</p>
            </div>
            <span className={`qx-driver-strength-badge qx-driver-strength-${primary.strength?.toLowerCase()}`}>
              {primary.strength}
            </span>
          </div>

          <div className="qx-driver-metrics">
            <div>
              <dt>Direction</dt>
              <dd className={`qx-driver-dir-${primary.direction?.toLowerCase()}`}>{primary.direction}</dd>
            </div>
            <div>
              <dt>Magnitude</dt>
              <dd>{typeof primary.magnitude === 'number' ? primary.magnitude.toFixed(1) : 'UNAVAILABLE'}</dd>
            </div>
            <div>
              <dt>Persistence</dt>
              <dd>{primary.persistence?.state ?? 'UNAVAILABLE'}</dd>
            </div>
            <div>
              <dt>Active</dt>
              <dd>{formatDuration(primary.persistence?.minutes_active)}</dd>
            </div>
          </div>
        </div>
      ) : (
        <div className="qx-driver-sub-threshold">
          <Minus size={13}/>
          <span>Sub-threshold — no driver meets activation hurdle. Market is in low-conviction equilibrium.</span>
        </div>
      )}

      {secondaries.length > 0 && (
        <div className="qx-driver-secondaries">
          <span className="qx-driver-secondaries-label">Secondary</span>
          {secondaries.map(sd => (
            <span key={sd.driver_id} className={`qx-driver-secondary-chip qx-driver-strength-${sd.strength?.toLowerCase()}`}>
              {formatArchetype(sd.driver_id)}
            </span>
          ))}
        </div>
      )}

      {(confirming.length > 0 || conflicting.length > 0) && (
        <details className="qx-driver-evidence-detail">
          <summary>Evidence ({confirming.length} confirming, {conflicting.length} conflicting)</summary>
          {confirming.length > 0 && (
            <div className="qx-driver-evidence-group qx-driver-confirming">
              <span>Confirming</span>
              {confirming.slice(0, 4).map(ev => (
                <div key={ev.evidence_id} className="qx-driver-evidence-item">
                  <CheckCircle2 size={10}/>
                  <span>{ev.label}</span>
                  <small>{ev.source}</small>
                </div>
              ))}
            </div>
          )}
          {conflicting.length > 0 && (
            <div className="qx-driver-evidence-group qx-driver-conflicting">
              <span>Conflicting</span>
              {conflicting.slice(0, 3).map(ev => (
                <div key={ev.evidence_id} className="qx-driver-evidence-item">
                  <AlertTriangle size={10}/>
                  <span>{ev.label}</span>
                  <small>{ev.source}</small>
                </div>
              ))}
            </div>
          )}
        </details>
      )}

      {coverage?.missing_sources?.length > 0 && (
        <div className="qx-driver-missing">
          <AlertTriangle size={11}/>
          <span>Missing: {coverage.missing_sources.join(', ')}</span>
        </div>
      )}
    </div>
  );
}

function CompactDriver({primary, status, coverage}) {
  if (!primary) {
    return (
      <div className="qx-driver-compact qx-driver-compact-unavailable">
        <Minus size={12}/>
        <span>SUB-THRESHOLD</span>
        <small>Low conviction</small>
      </div>
    );
  }
  return (
    <div className={`qx-driver-compact qx-driver-compact-${primary.strength?.toLowerCase()}`}>
      <StrengthIcon strength={primary.strength} direction={primary.direction} size={13}/>
      <strong>{formatArchetype(primary.driver_id)}</strong>
      <span className={`qx-driver-strength-badge qx-driver-strength-${primary.strength?.toLowerCase()}`}>
        {primary.strength}
      </span>
      {coverage && (
        <small>{coverage.observed_sources}/{coverage.required_sources} src</small>
      )}
    </div>
  );
}

function DriverUnavailable({symbol, compact, blockedReason, driverReasons = [], status = 'UNAVAILABLE'}) {
  const reason = humanizeReason(blockedReason, driverReasons, status);

  if (compact) {
    return (
      <div className="qx-driver-compact qx-driver-compact-unavailable qx-today-unavailable">
        <Minus size={12}/>
        <span>UNAVAILABLE</span>
        <small title={reason}>{blockedReason ? reason : 'No driver is inferred without canonical evidence.'}</small>
      </div>
    );
  }

  return (
    <div className="qx-driver-unavailable">
      <Activity size={14}/>
      <div>
        <strong>MARKET DRIVER UNAVAILABLE</strong>
        <p>{reason}</p>
        {driverReasons.length > 0 && (
          <small>{driverReasons.slice(0, 2).join(' · ')}</small>
        )}
      </div>
    </div>
  );
}

function StrengthIcon({strength, direction, size = 14}) {
  if (direction === 'BEARISH') return <TrendingDown size={size} className="qx-driver-dir-bearish"/>;
  if (direction === 'BULLISH') return <TrendingUp size={size} className="qx-driver-dir-bullish"/>;
  return <Zap size={size} className="qx-driver-dir-mixed"/>;
}

/** Humanize backend reason codes into plain English */
function humanizeReason(blockedReason, driverReasons, status) {
  if (blockedReason === 'NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP' || blockedReason === 'STALE_BARS') {
    return 'Outside market hours — no current bar data available. Driver resumes at market open.';
  }
  if (blockedReason === 'PIPELINE_BLOCKED') {
    return 'Canonical pipeline blocked. Check System for data health.';
  }
  if (driverReasons.includes('INSUFFICIENT_COVERAGE')) {
    return 'Insufficient evidence coverage — underlying or index data unavailable.';
  }
  if (driverReasons.includes('SUB_THRESHOLD')) {
    return 'No candidate driver meets the activation threshold. Market in equilibrium.';
  }
  if (status === 'PARTIAL') {
    return 'Partial evidence — driver present but missing some source families.';
  }
  return 'Backend market driver result not available for this evaluation.';
}

/** Formats archetype IDs like INDEX_RISK_ON → Index Risk On */
function formatArchetype(id) {
  if (!id) return 'UNAVAILABLE';
  return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatDuration(minutes) {
  if (minutes == null || !Number.isFinite(minutes)) return 'UNAVAILABLE';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function shortTime(isoString) {
  if (!isoString) return 'UNAVAILABLE';
  try {
    return new Date(isoString).toLocaleTimeString(undefined, {hour: '2-digit', minute: '2-digit'});
  } catch {
    return isoString;
  }
}
