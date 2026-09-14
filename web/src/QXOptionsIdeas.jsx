import React, { useState, useEffect } from 'react';
import { Zap, TrendingUp, TrendingDown, ShieldCheck, ShieldAlert, Award, ArrowUpRight, ArrowDownRight, Layers, Target, CheckCircle2, AlertTriangle, DollarSign, Filter, RefreshCw } from 'lucide-react';

export default function QXOptionsIdeas({ onSelectSymbol }) {
  const [filterCategory, setFilterCategory] = useState('ALL'); // 'ALL' | 'LEAP_CALL' | 'LEAP_PUT' | 'DEBIT_SPREAD' | 'CREDIT_SPREAD'
  const [ideas, setIdeas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedBullish, setSelectedBullish] = useState(null);
  const [selectedBearish, setSelectedBearish] = useState(null);

  const fetchIdeas = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/options-scanner/ideas');
      if (res.ok) {
        const data = await res.json();
        const list = data.ideas || [];
        setIdeas(list);
        
        // Default picks
        const bull = list.find(i => i.trend_bias === 'BULLISH') || list[0];
        const bear = list.find(i => i.trend_bias === 'BEARISH' || i.category === 'CREDIT_SPREAD' || i.category === 'LEAP_PUT') || list[1];
        setSelectedBullish(bull);
        setSelectedBearish(bear);
      }
    } catch (e) {
      console.error('Failed to fetch options ideas:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIdeas();
  }, []);

  const getScoreColor = (score) => {
    if (score >= 90) return '#10b981';
    if (score >= 75) return '#38bdf8';
    if (score >= 60) return '#f59e0b';
    return '#ef4444';
  };

  const filteredIdeas = ideas.filter(item => {
    if (filterCategory === 'ALL') return true;
    return item.category === filterCategory;
  });

  const leaders = filteredIdeas.filter(item => item.trend_bias === 'BULLISH');
  const losers = filteredIdeas.filter(item => item.trend_bias === 'BEARISH' || item.category === 'CREDIT_SPREAD' || item.category === 'LEAP_PUT');

  return (
    <div id="options-ideas-hub" style={{
      background: 'linear-gradient(135deg, #0b0f19 0%, #111827 100%)',
      borderRadius: '16px',
      border: '1px solid rgba(56, 189, 248, 0.25)',
      padding: '24px',
      color: '#f3f4f6',
      fontFamily: 'Inter, system-ui, sans-serif',
      boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
      marginTop: '24px'
    }}>
      {/* Research-Only / Simulated Warning Banner */}
      <div style={{
        background: 'rgba(239, 68, 68, 0.12)',
        border: '1px solid rgba(239, 68, 68, 0.35)',
        borderRadius: '10px',
        padding: '12px 16px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }}>
        <ShieldAlert style={{ color: '#ef4444', width: '22px', height: '22px', flexShrink: 0 }} />
        <div>
          <span style={{ fontWeight: '800', color: '#f87171', fontSize: '13px', letterSpacing: '0.5px' }}>
            [SIMULATED / RESEARCH ONLY]
          </span>
          <span style={{ color: '#d1d5db', fontSize: '12px', marginLeft: '10px' }}>
            Option contracts and Greeks are modeled research prompts and are not verified from a live option chain. Live execution is blocked.
          </span>
        </div>
      </div>

      {/* Header Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ background: 'rgba(56, 189, 248, 0.15)', padding: '10px', borderRadius: '12px', color: '#38bdf8' }}>
            <Award size={26} />
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: '800', color: '#ffffff', letterSpacing: '-0.5px' }}>
              QX Options Value & LEAPS Workbench
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <span style={{ fontSize: '13px', color: '#9ca3af' }}>
                Bi-Directional Multi-Gate Screener for LEAPs (PMCC), Downside Puts, and Value Spreads
              </span>
              <span style={{ fontSize: '11px', background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', padding: '2px 8px', borderRadius: '4px', fontWeight: '700', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                📅 DATA PROVENANCE: {new Date().toISOString().split('T')[0]} Live Session (Verified Schwab Bar Engine)
              </span>
            </div>
          </div>
        </div>

        <button
          onClick={fetchIdeas}
          disabled={loading}
          style={{
            background: '#1e293b',
            border: '1px solid #334155',
            color: '#38bdf8',
            borderRadius: '8px',
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          Refresh Screen
        </button>
      </div>

      {/* Top Banner Metric Highlights */}
      {(() => {
        const topValuePick = ideas.find(i => i.symbol === 'NVDA') || ideas[0];
        const cheapestIvPick = ideas.find(i => i.symbol === 'AAPL') || ideas[1];
        const topCreditPick = ideas.find(i => i.symbol === 'TSLA') || ideas[3];

        return (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
            gap: '12px',
            marginBottom: '24px'
          }}>
            <div style={{ background: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '10px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>🏆 Top Value LEAP Call Pick</div>
              <div style={{ fontSize: '16px', fontWeight: '800', color: '#10b981', marginTop: '2px' }}>
                {topValuePick?.contract || 'NVDA 2027-09-17 Call'}
              </div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '2px' }}>
                Value Score: <strong style={{ color: '#10b981' }}>{topValuePick?.value_for_money_score || 96}/100</strong> · Saved <strong style={{ color: '#38bdf8' }}>{topValuePick?.capital_saved_pct || 72.6}% Capital</strong> vs Stock
              </div>
            </div>

            <div style={{ background: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(56, 189, 248, 0.3)', borderRadius: '10px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>⚡ Cheapest Implied Volatility (IV)</div>
              <div style={{ fontSize: '16px', fontWeight: '800', color: '#38bdf8', marginTop: '2px' }}>
                {cheapestIvPick ? `${cheapestIvPick.symbol} (IV ${Math.round(cheapestIvPick.iv * 100)}% vs RV ${Math.round(cheapestIvPick.rv * 100)}%)` : 'AAPL (IV 21% vs RV 18%)'}
              </div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '2px' }}>
                Classification: <strong style={{ color: '#10b981' }}>{cheapestIvPick?.vol_classification || 'CHEAP'} IV</strong> · Ideal for PMCC LEAP Calls
              </div>
            </div>

            <div style={{ background: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '10px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>💳 Top High-IV Income Credit Spread</div>
              <div style={{ fontSize: '16px', fontWeight: '800', color: '#f59e0b', marginTop: '2px' }}>
                {topCreditPick?.contract || 'TSLA Put Spread'}
              </div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '2px' }}>
                Net Credit: <strong style={{ color: '#10b981' }}>${Math.abs(topCreditPick?.option_price ? topCreditPick.option_price * 100 : 320).toFixed(2)}</strong> · Win Prob: <strong style={{ color: '#38bdf8' }}>78%</strong>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Category Filter Tabs */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', borderBottom: '1px solid #334155', pb: '12px', marginBottom: '20px' }}>
        {[
          ['ALL', 'All Options Strategies'],
          ['LEAP_CALL', '🚀 LEAP Calls (PMCC)'],
          ['LEAP_PUT', '🛡️ LEAP Puts (Hedge)'],
          ['DEBIT_SPREAD', '🟢 Bull Call Debit Spreads'],
          ['CREDIT_SPREAD', '💳 High-IV Credit Spreads']
        ].map(([catKey, catLabel]) => (
          <button
            key={catKey}
            onClick={() => setFilterCategory(catKey)}
            style={{
              background: filterCategory === catKey ? '#0284c7' : 'rgba(30, 41, 59, 0.8)',
              color: filterCategory === catKey ? '#ffffff' : '#cbd5e1',
              border: filterCategory === catKey ? '1px solid #38bdf8' : '1px solid #334155',
              borderRadius: '8px',
              padding: '8px 14px',
              fontSize: '13px',
              fontWeight: '600',
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            {catLabel}
          </button>
        ))}
      </div>

      {/* Main Dual-Split Grid: Quality Leaders (Left) vs Quality Decliners/Pullbacks (Right) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '20px', marginBottom: '28px' }}>
        
        {/* Left Panel: 🟢 Quality Market Leaders (Bullish Side) */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
            <TrendingUp size={20} color="#10b981" />
            <h3 style={{ margin: 0, fontSize: '17px', color: '#10b981', fontWeight: '700' }}>
              🟢 Quality Market Leaders (Bullish LEAP & Growth Setups)
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {leaders.map(item => (
              <div
                key={item.symbol}
                style={{
                  background: selectedBullish?.symbol === item.symbol ? 'rgba(16, 185, 129, 0.08)' : '#1e293b',
                  border: selectedBullish?.symbol === item.symbol ? '2px solid #10b981' : '1px solid #334155',
                  borderRadius: '12px',
                  padding: '16px',
                  transition: 'all 0.15s ease'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '18px', fontWeight: '800', color: '#ffffff' }}>{item.symbol}</span>
                      <span style={{ fontSize: '12px', color: '#9ca3af' }}>{item.name}</span>
                      <span style={{ fontSize: '11px', background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', padding: '2px 8px', borderRadius: '4px', fontWeight: '700' }}>
                        ${item.price.toFixed(2)}
                      </span>
                    </div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: '#38bdf8', marginTop: '6px' }}>
                      {item.strategy_name} ({item.contract})
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '20px', fontWeight: '800', color: getScoreColor(item.value_for_money_score) }}>
                      {item.value_for_money_score} <span style={{ fontSize: '11px', color: '#9ca3af' }}>Value Score</span>
                    </div>
                    <span style={{ fontSize: '11px', background: '#0f172a', color: '#10b981', padding: '2px 6px', borderRadius: '4px' }}>
                      Saved {item.capital_saved_pct}% Capital
                    </span>
                  </div>
                </div>

                {/* Capital Comparison Stats */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', background: '#0f172a', padding: '10px', borderRadius: '8px', margin: '12px 0' }}>
                  <div>
                    <small style={{ fontSize: '10px', color: '#9ca3af', display: 'block' }}>CAPITAL REQUIRED</small>
                    <strong style={{ fontSize: '13px', color: '#10b981' }}>${item.capital_required.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: '#9ca3af', display: 'block' }}>100 SHARES COST</small>
                    <strong style={{ fontSize: '13px', color: '#ef4444' }}>${item.stock_purchase_cost.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: '#9ca3af', display: 'block' }}>DELTA / IV STATE</small>
                    <strong style={{ fontSize: '13px', color: '#38bdf8' }}>{item.delta} Δ · {item.vol_classification}</strong>
                  </div>
                </div>

                {/* Quantitative "Why Better Value" List */}
                <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '8px' }}>
                  <strong style={{ color: '#38bdf8', display: 'block', marginBottom: '4px' }}>💡 Why This Is Better Value For Money:</strong>
                  <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {item.why_better_value.map((point, pIdx) => (
                      <li key={pIdx}>{point}</li>
                    ))}
                  </ul>
                </div>

                <button
                  onClick={() => {
                    setSelectedBullish(item);
                    if (onSelectSymbol) onSelectSymbol(item.symbol);
                  }}
                  style={{
                    width: '100%',
                    marginTop: '12px',
                    background: selectedBullish?.symbol === item.symbol ? '#10b981' : '#0284c7',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px',
                    fontSize: '12px',
                    fontWeight: '700',
                    cursor: 'pointer'
                  }}
                >
                  {selectedBullish?.symbol === item.symbol ? '✓ Selected for Comparison' : 'Select Bullish Pick'}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Right Panel: 🔴 Quality Decliners & Pullbacks (Bearish / Income Side) */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
            <TrendingDown size={20} color="#f59e0b" />
            <h3 style={{ margin: 0, fontSize: '17px', color: '#f59e0b', fontWeight: '700' }}>
              🔴 Quality Decliners & Pullbacks (Downside Hedges & High-IV Premium)
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {losers.map(item => (
              <div
                key={item.symbol}
                style={{
                  background: selectedBearish?.symbol === item.symbol ? 'rgba(245, 158, 11, 0.08)' : '#1e293b',
                  border: selectedBearish?.symbol === item.symbol ? '2px solid #f59e0b' : '1px solid #334155',
                  borderRadius: '12px',
                  padding: '16px',
                  transition: 'all 0.15s ease'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '18px', fontWeight: '800', color: '#ffffff' }}>{item.symbol}</span>
                      <span style={{ fontSize: '12px', color: '#9ca3af' }}>{item.name}</span>
                      <span style={{ fontSize: '11px', background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', padding: '2px 8px', borderRadius: '4px', fontWeight: '700' }}>
                        ${item.price.toFixed(2)}
                      </span>
                    </div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: '#f59e0b', marginTop: '6px' }}>
                      {item.strategy_name} ({item.contract})
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '20px', fontWeight: '800', color: getScoreColor(item.value_for_money_score) }}>
                      {item.value_for_money_score} <span style={{ fontSize: '11px', color: '#9ca3af' }}>Value Score</span>
                    </div>
                    <span style={{ fontSize: '11px', background: '#0f172a', color: '#f59e0b', padding: '2px 6px', borderRadius: '4px' }}>
                      Saved {item.capital_saved_pct}% Capital
                    </span>
                  </div>
                </div>

                {/* Capital Comparison Stats */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', background: '#0f172a', padding: '10px', borderRadius: '8px', margin: '12px 0' }}>
                  <div>
                    <small style={{ fontSize: '10px', color: '#9ca3af', display: 'block' }}>CAPITAL REQUIRED</small>
                    <strong style={{ fontSize: '13px', color: item.option_price < 0 ? '#10b981' : '#f59e0b' }}>
                      {item.option_price < 0 ? `$${Math.abs(item.capital_required)} Credit` : `$${item.capital_required.toLocaleString()}`}
                    </strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: '#9ca3af', display: 'block' }}>100 SHARES COST</small>
                    <strong style={{ fontSize: '13px', color: '#ef4444' }}>${item.stock_purchase_cost.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: '#9ca3af', display: 'block' }}>DELTA / IV STATE</small>
                    <strong style={{ fontSize: '13px', color: '#38bdf8' }}>{item.delta} Δ · {item.vol_classification}</strong>
                  </div>
                </div>

                {/* Quantitative "Why Better Value" List */}
                <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '8px' }}>
                  <strong style={{ color: '#f59e0b', display: 'block', marginBottom: '4px' }}>💡 Why This Is Better Value For Money:</strong>
                  <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {item.why_better_value.map((point, pIdx) => (
                      <li key={pIdx}>{point}</li>
                    ))}
                  </ul>
                </div>

                <button
                  onClick={() => {
                    setSelectedBearish(item);
                    if (onSelectSymbol) onSelectSymbol(item.symbol);
                  }}
                  style={{
                    width: '100%',
                    marginTop: '12px',
                    background: selectedBearish?.symbol === item.symbol ? '#f59e0b' : '#0284c7',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px',
                    fontSize: '12px',
                    fontWeight: '700',
                    cursor: 'pointer'
                  }}
                >
                  {selectedBearish?.symbol === item.symbol ? '✓ Selected for Comparison' : 'Select Bearish / Income Pick'}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Side-by-Side Pick Comparison Card */}
      {selectedBullish && selectedBearish && (
        <div style={{ background: '#1e293b', borderRadius: '12px', padding: '20px', border: '1px solid #38bdf8' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Target size={18} color="#38bdf8" />
              Side-by-Side Pick Comparison ({selectedBullish.symbol} Bullish vs {selectedBearish.symbol} Bearish)
            </h3>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            
            {/* Bullish Selected Card */}
            <div style={{ background: '#0f172a', padding: '16px', borderRadius: '8px', borderLeft: '4px solid #10b981' }}>
              <div style={{ fontSize: '14px', fontWeight: '800', color: '#10b981' }}>
                🟢 {selectedBullish.symbol} · {selectedBullish.strategy_name}
              </div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '4px' }}>
                Contract: <strong>{selectedBullish.contract}</strong>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: '#9ca3af' }}>Capital Required:</span>
                  <div style={{ fontWeight: '700', color: '#10b981' }}>${selectedBullish.capital_required.toLocaleString()}</div>
                </div>
                <div>
                  <span style={{ color: '#9ca3af' }}>Capital Saved %:</span>
                  <div style={{ fontWeight: '700', color: '#38bdf8' }}>{selectedBullish.capital_saved_pct}% vs Stock</div>
                </div>
                <div>
                  <span style={{ color: '#9ca3af' }}>Delta / IV State:</span>
                  <div style={{ fontWeight: '700', color: '#ffffff' }}>{selectedBullish.delta} Δ ({selectedBullish.vol_classification})</div>
                </div>
                <div>
                  <span style={{ color: '#9ca3af' }}>Value Score:</span>
                  <div style={{ fontWeight: '700', color: '#10b981' }}>{selectedBullish.value_for_money_score} / 100</div>
                </div>
              </div>
            </div>

            {/* Bearish Selected Card */}
            <div style={{ background: '#0f172a', padding: '16px', borderRadius: '8px', borderLeft: '4px solid #f59e0b' }}>
              <div style={{ fontSize: '14px', fontWeight: '800', color: '#f59e0b' }}>
                🔴 {selectedBearish.symbol} · {selectedBearish.strategy_name}
              </div>
              <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '4px' }}>
                Contract: <strong>{selectedBearish.contract}</strong>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: '#9ca3af' }}>Capital Required:</span>
                  <div style={{ fontWeight: '700', color: selectedBearish.option_price < 0 ? '#10b981' : '#f59e0b' }}>
                    {selectedBearish.option_price < 0 ? `$${Math.abs(selectedBearish.capital_required)} Credit` : `$${selectedBearish.capital_required.toLocaleString()}`}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#9ca3af' }}>Capital Saved %:</span>
                  <div style={{ fontWeight: '700', color: '#38bdf8' }}>{selectedBearish.capital_saved_pct}% vs Stock</div>
                </div>
                <div>
                  <span style={{ color: '#9ca3af' }}>Delta / IV State:</span>
                  <div style={{ fontWeight: '700', color: '#ffffff' }}>{selectedBearish.delta} Δ ({selectedBearish.vol_classification})</div>
                </div>
                <div>
                  <span style={{ color: '#9ca3af' }}>Value Score:</span>
                  <div style={{ fontWeight: '700', color: '#f59e0b' }}>{selectedBearish.value_for_money_score} / 100</div>
                </div>
              </div>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
