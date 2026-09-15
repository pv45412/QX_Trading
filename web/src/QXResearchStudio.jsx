import React, { useState, useEffect } from 'react';
import { Search, TrendingUp, ShieldCheck, Activity, Layers, Sparkles, BarChart2, AlertTriangle, PlusCircle, MinusCircle } from 'lucide-react';

export default function QXResearchStudio({ defaultSymbol = 'NVDA' }) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [inputVal, setInputVal] = useState('');
  const [loading, setLoading] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);

  const fetchResearch = async (sym) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/market/${sym}/snapshot`);
      if (!res.ok) {
        throw new Error(`Research snapshot failed (${res.status})`);
      }
      const data = await res.json();
      setSnapshot(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResearch(symbol);
  }, [symbol]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (inputVal.trim()) {
      const s = inputVal.trim().toUpperCase();
      setSymbol(s);
      setInputVal('');
    }
  };

  const isBullish = snapshot?.structure?.current_trend === 'BULLISH';

  return (
    <section className="detail" id="research-studio" style={{ marginTop: '24px', marginBottom: '24px' }}>
      <div className="section-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <span style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--qx-accent)', textTransform: 'uppercase', letterSpacing: '1px' }}>
            AI POSITION DECISION & STRENGTH MATRIX STUDIO
          </span>
          <h2 style={{ margin: '4px 0 0 0', fontSize: '22px', color: 'var(--qx-text-heading)', fontWeight: '800', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={22} color="var(--qx-accent)" /> AI Position Research & Decision Studio
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: 'var(--qx-text-secondary)' }}>
            Evaluate underlying structural strengths, risk weaknesses, and clear rules for when to add or close a position.
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            placeholder="Search symbol (e.g. SPY, XLK, NVDA)..."
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            style={{
              padding: '8px 12px',
              background: 'var(--qx-bg-canvas)',
              border: '1px solid var(--qx-border)',
              borderRadius: '6px',
              color: 'var(--qx-text-primary)',
              fontSize: '13px',
              width: '240px'
            }}
          />
          <button
            type="submit"
            style={{
              padding: '8px 14px',
              background: 'var(--qx-bg-button)',
              border: '1px solid var(--qx-border)',
              borderRadius: '6px',
              color: 'var(--qx-text-heading)',
              fontSize: '13px',
              fontWeight: 'bold',
              cursor: 'pointer'
            }}
          >
            Research
          </button>
        </form>
      </div>

      <div style={{
        background: 'var(--qx-bg-surface)',
        border: '1px solid var(--qx-border)',
        borderRadius: '12px',
        padding: '20px'
      }}>
        {loading ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--qx-text-muted)' }}>
            Analyzing underlying structure and AI position evidence for {symbol}...
          </div>
        ) : error ? (
          <div style={{ padding: '20px', color: 'var(--qx-negative)', background: 'rgba(239,68,68,0.1)', borderRadius: '8px' }}>
            {error}
          </div>
        ) : snapshot ? (
          <div>
            {/* Top Overview Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginBottom: '20px' }}>
              <div style={{ background: 'var(--qx-bg-canvas)', padding: '14px', borderRadius: '8px', border: '1px solid var(--qx-border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--qx-text-muted)', textTransform: 'uppercase' }}>Active Instrument</div>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: 'var(--qx-text-heading)', marginTop: '2px' }}>{snapshot.symbol}</div>
                <div style={{ fontSize: '12px', color: 'var(--qx-positive)', marginTop: '2px' }}>Last: ${snapshot.last_price?.toFixed(2) || '—'}</div>
              </div>

              <div style={{ background: 'var(--qx-bg-canvas)', padding: '14px', borderRadius: '8px', border: '1px solid var(--qx-border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--qx-text-muted)', textTransform: 'uppercase' }}>Structural Trend</div>
                <div style={{ fontSize: '20px', fontWeight: 'bold', color: isBullish ? 'var(--qx-positive)' : 'var(--qx-negative)', marginTop: '2px' }}>
                  {snapshot.structure?.current_trend || 'NEUTRAL'}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--qx-text-muted)', marginTop: '2px' }}>
                  Structure Score: {snapshot.structure?.structure_score || 50}/100
                </div>
              </div>

              <div style={{ background: 'var(--qx-bg-canvas)', padding: '14px', borderRadius: '8px', border: '1px solid var(--qx-border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--qx-text-muted)', textTransform: 'uppercase' }}>Fair Value Gaps (FVG)</div>
                <div style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--qx-accent)', marginTop: '2px' }}>
                  {snapshot.structure?.active_fvgs?.length || 0} Active Zones
                </div>
                <div style={{ fontSize: '12px', color: 'var(--qx-text-muted)', marginTop: '2px' }}>
                  BOS: {snapshot.structure?.latest_bos || 'None'}
                </div>
              </div>
            </div>

            {/* AI Strengths vs Weaknesses Breakdown Matrix */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', marginBottom: '20px' }}>
              {/* Supporting Strengths */}
              <div style={{
                background: 'rgba(124, 169, 130, 0.08)',
                border: '1px solid rgba(124, 169, 130, 0.25)',
                borderRadius: '8px',
                padding: '16px'
              }}>
                <div style={{ fontSize: '13px', fontWeight: 'bold', color: 'var(--qx-positive)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                  <ShieldCheck size={18} /> Position Strengths (Supporting Bullish Factors)
                </div>
                <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: 'var(--qx-text-primary)', lineHeight: '1.6' }}>
                  <li>Higher swing high structural alignment above key moving averages.</li>
                  <li>Demand support backed by active Bullish Fair Value Gap (FVG) zones.</li>
                  <li>Positive Relative Strength (RS20) outperformance vs SPY benchmark.</li>
                  <li>Momentum RSI(14) maintaining positive structure without overbought saturation.</li>
                </ul>
              </div>

              {/* Weaknesses & Risks */}
              <div style={{
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                borderRadius: '8px',
                padding: '16px'
              }}>
                <div style={{ fontSize: '13px', fontWeight: 'bold', color: 'var(--qx-negative)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                  <AlertTriangle size={18} /> Position Weaknesses & Risk Drivers
                </div>
                <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: 'var(--qx-text-primary)', lineHeight: '1.6' }}>
                  <li>Approaching overhead supply resistance / potential Break of Structure (BOS).</li>
                  <li>IV Rank compression risk affecting long option premium values.</li>
                  <li>Short-term theta decay accelerating if price consolidates in chop zone.</li>
                  <li>Trailing stop invalidation level requires disciplined risk management.</li>
                </ul>
              </div>
            </div>

            {/* AI Decision Action Matrix: When to Close vs When to Add */}
            <div style={{
              background: 'var(--qx-bg-canvas)',
              border: '1px solid var(--qx-border)',
              borderRadius: '8px',
              padding: '18px'
            }}>
              <div style={{ fontSize: '13px', fontWeight: 'bold', color: 'var(--qx-accent)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px' }}>
                AI POSITION DECISION MATRIX
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '14px' }}>
                {/* Scale-In / Add Position Rules */}
                <div style={{ background: 'var(--qx-bg-surface)', padding: '14px', borderRadius: '6px', borderLeft: '4px solid var(--qx-positive)' }}>
                  <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--qx-positive)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <PlusCircle size={16} /> WHEN TO ADD TO POSITION (SCALE-IN)
                  </div>
                  <p style={{ margin: '6px 0 0 0', fontSize: '12px', color: 'var(--qx-text-primary)', lineHeight: '1.5' }}>
                    • Price pulls back to test Bullish FVG support zone with holding volume.<br />
                    • RSI resets to 45–50 level while structural uptrend remains intact.<br />
                    • Breakout confirmed above recent swing high on above-average RVOL.
                  </p>
                </div>

                {/* Close / Trim Position Rules */}
                <div style={{ background: 'var(--qx-bg-surface)', padding: '14px', borderRadius: '6px', borderLeft: '4px solid var(--qx-negative)' }}>
                  <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--qx-negative)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <MinusCircle size={16} /> WHEN TO TRIM / CLOSE POSITION
                  </div>
                  <p style={{ margin: '6px 0 0 0', fontSize: '12px', color: 'var(--qx-text-primary)', lineHeight: '1.5' }}>
                    • Price reaches initial 1-Sigma Expected Move or Target 1 profit level.<br />
                    • Bearish Break of Structure (BOS) occurs below key 20-day SMA support.<br />
                    • Relative Strength momentum breakdown occurs relative to SPY benchmark.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
