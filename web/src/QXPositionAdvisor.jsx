import React, { useState, useEffect } from 'react';
import { ShieldCheck, ShieldAlert, AlertTriangle, ArrowUpRight, TrendingUp, DollarSign, Activity, Target, Zap, RefreshCw, Layers } from 'lucide-react';

const POSITION_TYPES = [
  'Long Shares',
  'Short Shares',
  'Long Call',
  'Long Put',
  'Bull Call Spread',
  'Bear Put Spread',
];

function mapPosTypeToEngine(typeStr) {
  switch (typeStr) {
    case 'Long Call':
    case 'Bull Call Spread':
      return 'long_call';
    case 'Long Put':
    case 'Bear Put Spread':
      return 'long_put';
    case 'Short Shares':
      return 'short_call';
    case 'Long Shares':
    default:
      return 'long_stock';
  }
}

export default function QXPositionAdvisor({ defaultSymbol = 'VST' }) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [posType, setPosType] = useState('Long Shares');
  const [entryPrice, setEntryPrice] = useState(145.0);
  const [quantity, setQuantity] = useState(100);
  const [targetPrice, setTargetPrice] = useState(190.0);
  const [stopLoss, setStopLoss] = useState(130.0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);
  const [rollPlan, setRollPlan] = useState(null);

  useEffect(() => {
    evaluatePosition(symbol, posType, entryPrice, quantity, targetPrice, stopLoss);
  }, []);

  async function evaluatePosition(sym = symbol, type = posType, entry = entryPrice, qty = quantity, target = targetPrice, stop = stopLoss) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/position-advisor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: sym.trim().toUpperCase(),
          position_type: type,
          entry_price: parseFloat(entry) || 0.0,
          quantity: parseFloat(qty) || 100,
          target_price: parseFloat(target) || null,
          stop_loss: parseFloat(stop) || null,
        }),
      });
      if (!res.ok) {
        throw new Error(`Position research failed (${res.status})`);
      }
      const data = await res.json();
      setReport(data);

      // Fetch Roll Plan evaluation
      try {
        const rollRes = await fetch('/api/position-advisor/roll-plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: sym.trim().toUpperCase(),
            underlying_price: data.current_price || parseFloat(entry),
            position_type: mapPosTypeToEngine(type),
            current_strike: parseFloat(entry),
            current_dte: 30,
            current_premium: 3.50,
            iv: 0.30,
            trend_score: data.action_verdict === 'HOLD' ? 80 : 45,
            structure_score: data.action_verdict === 'HOLD' ? 75 : 45,
            invalidation_distance_pct: data.action_verdict === 'CLOSE / EXIT' ? 0.0 : 4.0,
            reward_remaining_pct: 45.0,
            momentum_score: 60.0,
            volatility_score: 60.0,
            stop_breached: data.action_verdict === 'CLOSE / EXIT',
            assignment_imminent: false
          })
        });
        if (rollRes.ok) {
          const rollData = await rollRes.json();
          setRollPlan(rollData);
        }
      } catch (rErr) {
        console.warn('Roll plan fetch deferred:', rErr);
      }

    } catch (err) {
      setError(err.message || 'Could not load position research report');
    } finally {
      setLoading(false);
    }
  }

  const verdictStyles = {
    'HOLD': { color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.4)', icon: ShieldCheck, emoji: '🟢' },
    'TRIM / TAKE PROFIT': { color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.4)', icon: AlertTriangle, emoji: '🟡' },
    'CLOSE / EXIT': { color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)', border: 'rgba(239, 68, 68, 0.4)', icon: ShieldAlert, emoji: '🔴' },
    'ROLL / ADJUST': { color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.12)', border: 'rgba(56, 189, 248, 0.4)', icon: Activity, emoji: '🔵' },
  };

  const currentVerdict = report ? report.action_verdict : 'HOLD';
  const style = verdictStyles[currentVerdict] || verdictStyles['HOLD'];

  return (
    <section className="detail" id="position-advisor" style={{ marginTop: '24px', marginBottom: '24px' }}>
      <div className="section-head" style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '12px' }}>
        <h2 style={{ fontSize: '18px', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
          <Zap size={20} /> 🎯 Automated Position Research & Action Advisor
        </h2>
        <span style={{ fontSize: '12px', color: '#94a3b8' }}>
          Realtime quantitative evaluation for open share & options positions
        </span>
      </div>

      {/* INPUT FORM CONTROLS */}
      <div style={{ background: '#111827', border: '1px solid #1f293d', borderRadius: '10px', padding: '16px', marginTop: '16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', alignItems: 'end' }}>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Ticker Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              style={{ width: '100%', padding: '8px', background: '#1f293d', border: '1px solid #374151', borderRadius: '6px', color: '#fff', fontSize: '14px', fontWeight: 'bold' }}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Position Type</label>
            <select
              value={posType}
              onChange={(e) => setPosType(e.target.value)}
              style={{ width: '100%', padding: '8px', background: '#1f293d', border: '1px solid #374151', borderRadius: '6px', color: '#fff', fontSize: '14px' }}
            >
              {POSITION_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Entry Price ($)</label>
            <input
              type="number"
              value={entryPrice}
              step="0.5"
              onChange={(e) => setEntryPrice(e.target.value)}
              style={{ width: '100%', padding: '8px', background: '#1f293d', border: '1px solid #374151', borderRadius: '6px', color: '#fff', fontSize: '14px' }}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Quantity / Contracts</label>
            <input
              type="number"
              value={quantity}
              step="10"
              onChange={(e) => setQuantity(e.target.value)}
              style={{ width: '100%', padding: '8px', background: '#1f293d', border: '1px solid #374151', borderRadius: '6px', color: '#fff', fontSize: '14px' }}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Target Price ($)</label>
            <input
              type="number"
              value={targetPrice}
              step="1.0"
              onChange={(e) => setTargetPrice(e.target.value)}
              style={{ width: '100%', padding: '8px', background: '#1f293d', border: '1px solid #374151', borderRadius: '6px', color: '#fff', fontSize: '14px' }}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Stop Loss ($)</label>
            <input
              type="number"
              value={stopLoss}
              step="1.0"
              onChange={(e) => setStopLoss(e.target.value)}
              style={{ width: '100%', padding: '8px', background: '#1f293d', border: '1px solid #374151', borderRadius: '6px', color: '#fff', fontSize: '14px' }}
            />
          </div>
        </div>

        <button
          onClick={() => evaluatePosition()}
          disabled={loading}
          style={{
            marginTop: '16px',
            width: '100%',
            padding: '10px',
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            border: '1px solid rgba(56, 189, 248, 0.35)',
            borderRadius: '6px',
            color: '#38bdf8',
            fontWeight: 'bold',
            fontSize: '14px',
            cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px'
          }}
        >
          {loading ? 'Evaluating Market & Technical Diagnostics...' : '⚡ Run Position Evaluation Research'}
        </button>
      </div>

      {error && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: '12px', borderRadius: '8px', color: '#ef4444', marginTop: '16px' }}>
          ⚠️ {error}
        </div>
      )}

      {/* VERDICT REPORT CARD */}
      {report && (
        <div style={{ marginTop: '20px' }}>
          <div style={{
            background: style.bg,
            border: `2px solid ${style.border}`,
            borderRadius: '10px',
            padding: '20px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '16px'
          }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 'bold', color: style.color, textTransform: 'uppercase', letterSpacing: '1px' }}>
                AUTOMATED POSITION VERDICT
              </div>
              <h2 style={{ margin: '4px 0 0 0', fontSize: '28px', color: '#fff', fontWeight: '800' }}>
                {style.emoji} {report.action_verdict} <span style={{ fontSize: '18px', color: '#94a3b8', fontWeight: 'normal' }}>({(Number(report?.confidence_score || 0) * 100).toFixed(0)}% Confidence)</span>
              </h2>
              <p style={{ margin: '8px 0 0 0', fontSize: '14px', color: '#cbd5e1', maxWidth: '650px' }}>
                {report.verdict_summary}
              </p>
            </div>

            <div style={{ textAlign: 'right', background: 'rgba(0,0,0,0.3)', padding: '12px 18px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: '12px', color: '#94a3b8' }}>Unrealized P&L</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: report.unrealized_pnl >= 0 ? '#00c853' : '#ff3d00' }}>
                {report.unrealized_pnl >= 0 ? '+' : ''}${report.unrealized_pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                <span style={{ fontSize: '14px', marginLeft: '6px' }}>
                  ({report.unrealized_pnl_pct >= 0 ? '+' : ''}{(Number(report?.unrealized_pnl_pct || 0) * 100).toFixed(1)}%)
                </span>
              </div>
            </div>
          </div>

          {/* ROLL & ADJUSTMENT RECOMMENDATION ENGINE CARD */}
          {rollPlan && rollPlan.recommendation && (
            <div style={{
              background: '#0f172a',
              border: '1px solid #1e293b',
              borderRadius: '10px',
              padding: '16px',
              marginTop: '16px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '10px' }}>
                <h3 style={{ margin: 0, fontSize: '15px', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <RefreshCw size={16} /> 🔄 Position Adjustment & Roll Engine Plan
                </h3>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', background: '#1e293b', color: '#cbd5e1', padding: '4px 8px', borderRadius: '4px', border: '1px solid #334155' }}>
                    Health Score: <b>{rollPlan.composite_health} / 100</b>
                  </span>
                  <span style={{
                    fontSize: '11px',
                    fontWeight: 'bold',
                    padding: '4px 10px',
                    borderRadius: '4px',
                    background: rollPlan.recommendation.roll_type === 'HOLD_NO_ACTION' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(56, 189, 248, 0.15)',
                    color: rollPlan.recommendation.roll_type === 'HOLD_NO_ACTION' ? '#10b981' : '#38bdf8',
                    border: rollPlan.recommendation.roll_type === 'HOLD_NO_ACTION' ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid rgba(56, 189, 248, 0.4)'
                  }}>
                    {rollPlan.recommendation.roll_type}
                  </span>
                </div>
              </div>

              <div style={{ fontSize: '13px', color: '#cbd5e1', marginBottom: '14px', lineHeight: '1.5' }}>
                📌 <b>Rationale:</b> {rollPlan.recommendation.rationale}
              </div>

              {rollPlan.recommendation.recommended_legs && rollPlan.recommendation.recommended_legs.length > 0 ? (
                <div>
                  <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 'bold', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Layers size={14} /> Execution Order Legs:
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                      <thead>
                        <tr style={{ background: '#1e293b', textAlign: 'left', color: '#94a3b8', fontSize: '11px' }}>
                          <th style={{ padding: '8px', borderRadius: '4px 0 0 4px' }}>ACTION</th>
                          <th style={{ padding: '8px' }}>TYPE</th>
                          <th style={{ padding: '8px' }}>STRIKE ($)</th>
                          <th style={{ padding: '8px' }}>TARGET DTE</th>
                          <th style={{ padding: '8px', textAlign: 'right', borderRadius: '0 4px 4px 0' }}>EST. PREMIUM</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rollPlan.recommendation.recommended_legs.map((leg, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                            <td style={{ padding: '8px', fontWeight: 'bold', color: leg.action.startsWith('BUY') ? '#38bdf8' : '#f59e0b' }}>
                              {leg.action}
                            </td>
                            <td style={{ padding: '8px', textTransform: 'uppercase', color: '#e2e8f0' }}>{leg.option_type}</td>
                            <td style={{ padding: '8px', color: '#fff', fontWeight: 'bold' }}>${(Number(leg?.strike) || 0).toFixed(2)}</td>
                            <td style={{ padding: '8px', color: '#94a3b8' }}>{leg.dte} Days</td>
                            <td style={{ padding: '8px', textAlign: 'right', color: '#fff', fontWeight: 'bold' }}>${(Number(leg?.estimated_premium) || 0).toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: '12px', color: '#94a3b8', fontStyle: 'italic', background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  ✓ Position health is strong. No leg execution adjustment required.
                </div>
              )}
            </div>
          )}

          {/* 4-CARD DIAGNOSTICS GRID */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginTop: '16px' }}>
            <div style={{ background: '#111827', border: '1px solid #1f293d', borderRadius: '8px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 'bold' }}>P&L & PRICE METRICS</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fff', marginTop: '4px' }}>${(Number(report?.current_price) || 0).toFixed(2)}</div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '4px' }}>Entry: <b>${(Number(report?.entry_price) || 0).toFixed(2)}</b></div>
              <div style={{ fontSize: '12px', color: '#cbd5e1' }}>Position: <b>{report.position_type}</b></div>
            </div>

            <div style={{ background: '#111827', border: '1px solid #1f293d', borderRadius: '8px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 'bold' }}>RISK : REWARD PARAMETERS</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fff', marginTop: '4px' }}>
                {report.risk_metrics?.risk_reward_ratio ? Number(report.risk_metrics.risk_reward_ratio).toFixed(2) : '1.50'}:1 R:R
              </div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '4px' }}>Stop Loss: <b>${(Number(report?.adjusted_stop_loss) || 0).toFixed(2)}</b></div>
              <div style={{ fontSize: '12px', color: '#cbd5e1' }}>Target Price: <b>${(Number(report?.adjusted_target_price) || 0).toFixed(2)}</b></div>
            </div>

            <div style={{ background: '#111827', border: '1px solid #1f293d', borderRadius: '8px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 'bold' }}>MOVING AVERAGE TREND</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fff', marginTop: '4px' }}>RSI: {report.technical_metrics?.rsi_14}</div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '4px' }}>SMA 20: <b>${report.technical_metrics?.sma_20}</b></div>
              <div style={{ fontSize: '12px', color: '#cbd5e1' }}>SMA 50: <b>${report.technical_metrics?.sma_50}</b></div>
            </div>

            <div style={{ background: '#111827', border: '1px solid #1f293d', borderRadius: '8px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 'bold' }}>VOLATILITY & RANGE</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fff', marginTop: '4px' }}>ATR: ${report.technical_metrics?.atr_14}</div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '4px' }}>52w High: <b>${report.technical_metrics?.high_52w}</b></div>
              <div style={{ fontSize: '12px', color: '#cbd5e1' }}>Off Peak: <b>{(Number(report?.technical_metrics?.pct_from_high || 0) * 100).toFixed(1)}%</b></div>
            </div>
          </div>

          {/* BULLISH VS BEARISH FACTORS */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px', marginTop: '16px' }}>
            <div style={{ background: '#111827', border: '1px solid #166534', borderRadius: '8px', padding: '14px' }}>
              <div style={{ fontSize: '13px', fontWeight: 'bold', color: '#4ade80', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                🟢 Supporting Bullish Factors
              </div>
              <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: '#e2e8f0', lineHeight: '1.6' }}>
                {report.positive_factors && report.positive_factors.length > 0 ? (
                  report.positive_factors.map((f, i) => <li key={i}>{f}</li>)
                ) : (
                  <li style={{ color: '#94a3b8' }}>No strong positive drivers detected.</li>
                )}
              </ul>
            </div>

            <div style={{ background: '#111827', border: '1px solid #991b1b', borderRadius: '8px', padding: '14px' }}>
              <div style={{ fontSize: '13px', fontWeight: 'bold', color: '#f87171', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                🔴 Bearish / Risk Factors
              </div>
              <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: '#e2e8f0', lineHeight: '1.6' }}>
                {report.negative_factors && report.negative_factors.length > 0 ? (
                  report.negative_factors.map((f, i) => <li key={i}>{f}</li>)
                ) : (
                  <li style={{ color: '#94a3b8' }}>No critical risk flags detected.</li>
                )}
              </ul>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
