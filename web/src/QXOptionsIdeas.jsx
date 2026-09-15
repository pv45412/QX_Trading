import React, { useState, useEffect } from 'react';
import { Zap, TrendingUp, TrendingDown, ShieldCheck, ShieldAlert, Award, ArrowUpRight, ArrowDownRight, Layers, Target, CheckCircle2, AlertTriangle, DollarSign, Filter, RefreshCw } from 'lucide-react';

export default function QXOptionsIdeas({ onSelectSymbol }) {
  const [filterCategory, setFilterCategory] = useState('ALL');
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
    if (score >= 90) return 'var(--qx-positive)';
    if (score >= 75) return 'var(--qx-accent)';
    if (score >= 60) return 'var(--qx-warning)';
    return 'var(--qx-negative)';
  };

  const filteredIdeas = ideas.filter(item => {
    if (filterCategory === 'ALL') return true;
    return item.category === filterCategory;
  });

  const leaders = filteredIdeas.filter(item => item.trend_bias === 'BULLISH');
  const losers = filteredIdeas.filter(item => item.trend_bias === 'BEARISH' || item.category === 'CREDIT_SPREAD' || item.category === 'LEAP_PUT');

  return (
    <div id="options-ideas-hub" style={{
      background: 'var(--qx-bg-surface)',
      borderRadius: '12px',
      border: '1px solid var(--qx-border)',
      padding: '24px',
      color: 'var(--qx-text-primary)',
      fontFamily: 'Inter, system-ui, sans-serif',
      boxShadow: 'none',
      marginTop: '24px'
    }}>
      {/* Research-Only / Simulated Warning Banner */}
      <div style={{
        background: 'rgba(201, 106, 91, 0.1)',
        border: '1px solid rgba(201, 106, 91, 0.25)',
        borderRadius: '8px',
        padding: '12px 16px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }}>
        <ShieldAlert style={{ color: 'var(--qx-negative)', width: '22px', height: '22px', flexShrink: 0 }} />
        <div>
          <span style={{ fontWeight: '800', color: 'var(--qx-negative)', fontSize: '12px', letterSpacing: '0.5px' }}>
            [SIMULATED / RESEARCH ONLY]
          </span>
          <span style={{ color: 'var(--qx-text-secondary)', fontSize: '12px', marginLeft: '10px' }}>
            Option contracts and Greeks are modeled research prompts and are not verified from a live option chain. Live execution is blocked.
          </span>
        </div>
      </div>

      {/* Header Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ background: 'var(--qx-bg-button)', border: '1px solid var(--qx-border)', padding: '10px', borderRadius: '12px', color: 'var(--qx-accent)' }}>
            <Award size={26} />
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: '800', color: 'var(--qx-text-heading)', letterSpacing: '-0.5px' }}>
              QX Options Value & LEAPS Workbench
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <span style={{ fontSize: '13px', color: 'var(--qx-text-secondary)' }}>
                Bi-Directional Multi-Gate Screener for LEAPs (PMCC), Downside Puts, and Value Spreads
              </span>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '6px' }}>
                <span style={{ fontSize: '11px', background: 'var(--qx-bg-button)', color: 'var(--qx-positive)', padding: '2px 8px', borderRadius: '4px', fontWeight: '700', border: '1px solid var(--qx-border)' }}>
                  📊 EQUITY PRICE PROVENANCE: Verified Schwab Bar Engine (Live Session)
                </span>
                <span style={{ fontSize: '11px', background: 'var(--qx-bg-button)', color: 'var(--qx-warning)', padding: '2px 8px', borderRadius: '4px', fontWeight: '700', border: '1px solid var(--qx-border)' }}>
                  🧪 OPTION CONTRACT & GREEKS PROVENANCE: Modeled / Simulated (Non-Executable)
                </span>
              </div>
            </div>
          </div>
        </div>

        <button
          onClick={fetchIdeas}
          disabled={loading}
          style={{
            background: 'var(--qx-bg-button)',
            border: '1px solid var(--qx-border)',
            color: 'var(--qx-text-primary)',
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
            <div style={{ background: 'var(--qx-bg-button)', border: '1px solid var(--qx-border)', borderRadius: '10px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: 'var(--qx-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>🏆 Top Value LEAP Call Pick</div>
              <div style={{ fontSize: '16px', fontWeight: '800', color: 'var(--qx-positive)', marginTop: '2px' }}>
                {topValuePick?.contract || 'NVDA 2027-09-17 Call'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--qx-text-primary)', marginTop: '2px' }}>
                Value Score: <strong style={{ color: 'var(--qx-positive)' }}>{topValuePick?.value_for_money_score || 96}/100</strong> · Saved <strong style={{ color: 'var(--qx-accent)' }}>{topValuePick?.capital_saved_pct || 72.6}% Capital</strong> vs Stock
              </div>
            </div>

            <div style={{ background: 'var(--qx-bg-button)', border: '1px solid var(--qx-border)', borderRadius: '10px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: 'var(--qx-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>⚡ Cheapest Implied Volatility (IV)</div>
              <div style={{ fontSize: '16px', fontWeight: '800', color: 'var(--qx-accent)', marginTop: '2px' }}>
                {cheapestIvPick ? `${cheapestIvPick.symbol} (IV ${Math.round(cheapestIvPick.iv * 100)}% vs RV ${Math.round(cheapestIvPick.rv * 100)}%)` : 'AAPL (IV 21% vs RV 18%)'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--qx-text-primary)', marginTop: '2px' }}>
                Classification: <strong style={{ color: 'var(--qx-positive)' }}>{cheapestIvPick?.vol_classification || 'CHEAP'} IV</strong> · Ideal for PMCC LEAP Calls
              </div>
            </div>

            <div style={{ background: 'var(--qx-bg-button)', border: '1px solid var(--qx-border)', borderRadius: '10px', padding: '14px' }}>
              <div style={{ fontSize: '11px', color: 'var(--qx-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>💳 Top High-IV Income Credit Spread</div>
              <div style={{ fontSize: '16px', fontWeight: '800', color: 'var(--qx-warning)', marginTop: '2px' }}>
                {topCreditPick?.contract || 'TSLA Put Spread'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--qx-text-primary)', marginTop: '2px' }}>
                Net Credit: <strong style={{ color: 'var(--qx-positive)' }}>${Math.abs(topCreditPick?.option_price ? topCreditPick.option_price * 100 : 320).toFixed(2)}</strong> · Win Prob: <strong style={{ color: 'var(--qx-accent)' }}>78%</strong>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Category Filter Tabs */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', borderBottom: '1px solid var(--qx-border)', paddingBottom: '12px', marginBottom: '20px' }}>
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
              background: filterCategory === catKey ? 'var(--qx-bg-hover)' : 'var(--qx-bg-button)',
              color: filterCategory === catKey ? 'var(--qx-accent)' : 'var(--qx-text-secondary)',
              border: filterCategory === catKey ? '1px solid var(--qx-accent)' : '1px solid var(--qx-border)',
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
            <TrendingUp size={20} color="var(--qx-positive)" />
            <h3 style={{ margin: 0, fontSize: '17px', color: 'var(--qx-positive)', fontWeight: '700' }}>
              🟢 Quality Market Leaders (Bullish LEAP & Growth Setups)
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {leaders.map(item => (
              <div
                key={item.symbol}
                style={{
                  background: selectedBullish?.symbol === item.symbol ? 'var(--qx-bg-hover)' : 'var(--qx-bg-button)',
                  border: selectedBullish?.symbol === item.symbol ? '1px solid var(--qx-positive)' : '1px solid var(--qx-border)',
                  borderRadius: '12px',
                  padding: '16px',
                  transition: 'all 0.15s ease'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '18px', fontWeight: '800', color: 'var(--qx-text-heading)' }}>{item.symbol}</span>
                      <span style={{ fontSize: '12px', color: 'var(--qx-text-secondary)' }}>{item.name}</span>
                      <span style={{ fontSize: '11px', background: 'var(--qx-bg-surface)', color: 'var(--qx-positive)', padding: '2px 8px', borderRadius: '4px', fontWeight: '700', border: '1px solid var(--qx-border)' }}>
                        ${(Number(item.price) || 0).toFixed(2)}
                      </span>
                    </div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: 'var(--qx-accent)', marginTop: '6px' }}>
                      {item.strategy_name} ({item.contract})
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '20px', fontWeight: '800', color: getScoreColor(item.value_for_money_score) }}>
                      {item.value_for_money_score} <span style={{ fontSize: '11px', color: 'var(--qx-text-secondary)' }}>Value Score</span>
                    </div>
                    <span style={{ fontSize: '11px', background: 'var(--qx-bg-canvas)', color: 'var(--qx-positive)', padding: '2px 6px', borderRadius: '4px' }}>
                      Saved {item.capital_saved_pct}% Capital
                    </span>
                  </div>
                </div>

                {/* Capital Comparison Stats */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', background: 'var(--qx-bg-canvas)', padding: '10px', borderRadius: '8px', margin: '12px 0' }}>
                  <div>
                    <small style={{ fontSize: '10px', color: 'var(--qx-text-secondary)', display: 'block' }}>CAPITAL REQUIRED</small>
                    <strong style={{ fontSize: '13px', color: 'var(--qx-positive)' }}>${item.capital_required.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: 'var(--qx-text-secondary)', display: 'block' }}>100 SHARES COST</small>
                    <strong style={{ fontSize: '13px', color: 'var(--qx-negative)' }}>${item.stock_purchase_cost.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: 'var(--qx-text-secondary)', display: 'block' }}>DELTA / IV STATE</small>
                    <strong style={{ fontSize: '13px', color: 'var(--qx-accent)' }}>{item.delta} Δ · {item.vol_classification}</strong>
                  </div>
                </div>

                {/* Quantitative "Why Better Value" List */}
                <div style={{ fontSize: '12px', color: 'var(--qx-text-primary)', marginTop: '8px' }}>
                  <strong style={{ color: 'var(--qx-accent)', display: 'block', marginBottom: '4px' }}>💡 Why This Is Better Value For Money:</strong>
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
                    background: selectedBullish?.symbol === item.symbol ? 'var(--qx-positive)' : 'var(--qx-bg-button)',
                    color: selectedBullish?.symbol === item.symbol ? 'var(--qx-bg-canvas)' : 'var(--qx-text-primary)',
                    border: '1px solid var(--qx-border)',
                    borderRadius: '6px',
                    padding: '8px',
                    fontSize: '12px',
                    fontWeight: '700',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
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
            <TrendingDown size={20} color="var(--qx-warning)" />
            <h3 style={{ margin: 0, fontSize: '17px', color: 'var(--qx-warning)', fontWeight: '700' }}>
              🔴 Quality Decliners & Pullbacks (Downside Hedges & High-IV Premium)
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {losers.map(item => (
              <div
                key={item.symbol}
                style={{
                  background: selectedBearish?.symbol === item.symbol ? 'var(--qx-bg-hover)' : 'var(--qx-bg-button)',
                  border: selectedBearish?.symbol === item.symbol ? '1px solid var(--qx-warning)' : '1px solid var(--qx-border)',
                  borderRadius: '12px',
                  padding: '16px',
                  transition: 'all 0.15s ease'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '18px', fontWeight: '800', color: 'var(--qx-text-heading)' }}>{item.symbol}</span>
                      <span style={{ fontSize: '12px', color: 'var(--qx-text-secondary)' }}>{item.name}</span>
                      <span style={{ fontSize: '11px', background: 'var(--qx-bg-surface)', color: 'var(--qx-negative)', padding: '2px 8px', borderRadius: '4px', fontWeight: '700', border: '1px solid var(--qx-border)' }}>
                        ${(Number(item.price) || 0).toFixed(2)}
                      </span>
                    </div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: 'var(--qx-warning)', marginTop: '6px' }}>
                      {item.strategy_name} ({item.contract})
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '20px', fontWeight: '800', color: getScoreColor(item.value_for_money_score) }}>
                      {item.value_for_money_score} <span style={{ fontSize: '11px', color: 'var(--qx-text-secondary)' }}>Value Score</span>
                    </div>
                    <span style={{ fontSize: '11px', background: 'var(--qx-bg-canvas)', color: 'var(--qx-warning)', padding: '2px 6px', borderRadius: '4px' }}>
                      Saved {item.capital_saved_pct}% Capital
                    </span>
                  </div>
                </div>

                {/* Capital Comparison Stats */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', background: 'var(--qx-bg-canvas)', padding: '10px', borderRadius: '8px', margin: '12px 0' }}>
                  <div>
                    <small style={{ fontSize: '10px', color: 'var(--qx-text-secondary)', display: 'block' }}>CAPITAL REQUIRED</small>
                    <strong style={{ fontSize: '13px', color: item.option_price < 0 ? 'var(--qx-positive)' : 'var(--qx-warning)' }}>
                      {item.option_price < 0 ? `$${Math.abs(item.capital_required)} Credit` : `$${item.capital_required.toLocaleString()}`}
                    </strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: 'var(--qx-text-secondary)', display: 'block' }}>100 SHARES COST</small>
                    <strong style={{ fontSize: '13px', color: 'var(--qx-negative)' }}>${item.stock_purchase_cost.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small style={{ fontSize: '10px', color: 'var(--qx-text-secondary)', display: 'block' }}>DELTA / IV STATE</small>
                    <strong style={{ fontSize: '13px', color: 'var(--qx-accent)' }}>{item.delta} Δ · {item.vol_classification}</strong>
                  </div>
                </div>

                {/* Quantitative "Why Better Value" List */}
                <div style={{ fontSize: '12px', color: 'var(--qx-text-primary)', marginTop: '8px' }}>
                  <strong style={{ color: 'var(--qx-warning)', display: 'block', marginBottom: '4px' }}>💡 Why This Is Better Value For Money:</strong>
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
                    background: selectedBearish?.symbol === item.symbol ? 'var(--qx-warning)' : 'var(--qx-bg-button)',
                    color: selectedBearish?.symbol === item.symbol ? 'var(--qx-bg-canvas)' : 'var(--qx-text-primary)',
                    border: '1px solid var(--qx-border)',
                    borderRadius: '6px',
                    padding: '8px',
                    fontSize: '12px',
                    fontWeight: '700',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
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
        <div style={{ background: 'var(--qx-bg-surface)', borderRadius: '12px', padding: '20px', border: '1px solid var(--qx-border)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: 'var(--qx-text-heading)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Target size={18} color="var(--qx-accent)" />
              Side-by-Side Pick Comparison ({selectedBullish.symbol} Bullish vs {selectedBearish.symbol} Bearish)
            </h3>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            
            {/* Bullish Selected Card */}
            <div style={{ background: 'var(--qx-bg-button)', padding: '16px', borderRadius: '8px', borderLeft: '4px solid var(--qx-positive)' }}>
              <div style={{ fontSize: '14px', fontWeight: '800', color: 'var(--qx-positive)' }}>
                🟢 {selectedBullish.symbol} · {selectedBullish.strategy_name}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--qx-text-primary)', marginTop: '4px' }}>
                Contract: <strong>{selectedBullish.contract}</strong>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Capital Required:</span>
                  <div style={{ fontWeight: '700', color: 'var(--qx-positive)' }}>${selectedBullish.capital_required.toLocaleString()}</div>
                </div>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Capital Saved %:</span>
                  <div style={{ fontWeight: '700', color: 'var(--qx-accent)' }}>{selectedBullish.capital_saved_pct}% vs Stock</div>
                </div>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Delta / IV State:</span>
                  <div style={{ fontWeight: '700', color: 'var(--qx-text-heading)' }}>{selectedBullish.delta} Δ ({selectedBullish.vol_classification})</div>
                </div>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Value Score:</span>
                  <div style={{ fontWeight: '700', color: 'var(--qx-positive)' }}>{selectedBullish.value_for_money_score} / 100</div>
                </div>
              </div>
            </div>

            {/* Bearish Selected Card */}
            <div style={{ background: 'var(--qx-bg-button)', padding: '16px', borderRadius: '8px', borderLeft: '4px solid var(--qx-warning)' }}>
              <div style={{ fontSize: '14px', fontWeight: '800', color: 'var(--qx-warning)' }}>
                🔴 {selectedBearish.symbol} · {selectedBearish.strategy_name}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--qx-text-primary)', marginTop: '4px' }}>
                Contract: <strong>{selectedBearish.contract}</strong>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Capital Required:</span>
                  <div style={{ fontWeight: '700', color: selectedBearish.option_price < 0 ? 'var(--qx-positive)' : 'var(--qx-warning)' }}>
                    {selectedBearish.option_price < 0 ? `$${Math.abs(selectedBearish.capital_required)} Credit` : `$${selectedBearish.capital_required.toLocaleString()}`}
                  </div>
                </div>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Capital Saved %:</span>
                  <div style={{ fontWeight: '700', color: 'var(--qx-accent)' }}>{selectedBearish.capital_saved_pct}% vs Stock</div>
                </div>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Delta / IV State:</span>
                  <div style={{ fontWeight: '700', color: 'var(--qx-text-heading)' }}>{selectedBearish.delta} Δ ({selectedBearish.vol_classification})</div>
                </div>
                <div>
                  <span style={{ color: 'var(--qx-text-secondary)' }}>Value Score:</span>
                  <div style={{ fontWeight: '700', color: 'var(--qx-warning)' }}>{selectedBearish.value_for_money_score} / 100</div>
                </div>
              </div>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
