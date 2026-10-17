import React, { useState, useEffect } from 'react';

const STRATEGY_PRESETS = [
  { id: 'bull-call', name: 'Bull Call Debit Spread', icon: '📈' },
  { id: 'spx-calendar', name: 'SPX Calendar Spread', icon: '📅' },
  { id: 'pmcc', name: "PMCC (Poor Man's Covered Call)", icon: '👑' },
  { id: 'wheel', name: 'The Wheel Strategy', icon: '⚙️' },
  { id: 'iron-condor', name: 'Iron Condor', icon: '🦅' }
];

export default function QXStrategyWorkspaces() {
  const [activeStrategy, setActiveStrategy] = useState('bull-call');
  const [underlyingPrice, setUnderlyingPrice] = useState(148.53);
  const [symbol, setSymbol] = useState('VST');
  const [workspaceInfo, setWorkspaceInfo] = useState(null);
  const [legs, setLegs] = useState([]);
  const [payoffData, setPayoffData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch workspace preset when active strategy changes
  useEffect(() => {
    async function loadWorkspace() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/strategies/workspace/${activeStrategy}`);
        if (!res.ok) throw new Error('Failed to load strategy workspace preset');
        const data = await res.json();
        setWorkspaceInfo(data);
        setLegs(data.preset_legs || []);
      } catch (err) {
        console.error(err);
        setError('Using local fallback workspace configuration.');
      } finally {
        setLoading(false);
      }
    }
    loadWorkspace();
  }, [activeStrategy]);

  // Recalculate payoff curve whenever legs or underlying price change
  useEffect(() => {
    if (legs.length === 0) return;

    async function calculatePayoff() {
      try {
        const res = await fetch('/api/strategies/payoff', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            strategy_name: workspaceInfo?.strategy_name || activeStrategy,
            underlying_price: parseFloat(underlyingPrice) || 100.0,
            legs: legs
          })
        });
        if (res.ok) {
          const data = await res.json();
          setPayoffData(data);
        }
      } catch (err) {
        console.error('Payoff calculation error:', err);
      }
    }

    const timer = setTimeout(calculatePayoff, 200);
    return () => clearTimeout(timer);
  }, [legs, underlyingPrice, activeStrategy, workspaceInfo]);

  const handleLegChange = (index, field, value) => {
    const updated = [...legs];
    updated[index] = {
      ...updated[index],
      [field]: field === 'action' || field === 'option_type' ? value : parseFloat(value) || 0
    };
    setLegs(updated);
  };

  const addLeg = () => {
    setLegs([
      ...legs,
      { option_type: 'call', action: 'buy', strike: Math.round(underlyingPrice), premium: 2.5, quantity: 1, dte: 30 }
    ]);
  };

  const removeLeg = (index) => {
    setLegs(legs.filter((_, i) => i !== index));
  };

  // Render SVG Payoff Curve Diagram
  const renderPayoffSvg = () => {
    if (!payoffData || !payoffData.curve || payoffData.curve.length === 0) return null;

    const curve = payoffData.curve;
    const width = 800;
    const height = 280;
    const padding = 45;

    const minPrice = curve[0].underlying_price;
    const maxPrice = curve[curve.length - 1].underlying_price;
    const pnlValues = curve.map((p) => p.pnl_dollars);
    const minPnl = Math.min(...pnlValues, -50);
    const maxPnl = Math.max(...pnlValues, 50);

    const mapX = (price) => padding + ((price - minPrice) / (maxPrice - minPrice)) * (width - 2 * padding);
    const mapY = (pnl) => height - padding - ((pnl - minPnl) / (maxPnl - minPnl)) * (height - 2 * padding);

    const zeroY = mapY(0);
    const spotX = mapX(underlyingPrice);

    const pointsString = curve.map((p) => `${mapX(p.underlying_price)},${mapY(p.pnl_dollars)}`).join(' ');

    return (
      <div className="relative bg-slate-900/90 rounded-xl p-4 border border-slate-800 shadow-inner" style={{ background: 'var(--qx-bg-surface)', border: '1px solid var(--qx-border)' }}>
        <div className="flex justify-between items-center mb-2 px-2 text-xs font-semibold tracking-wider text-slate-400 uppercase">
          <span style={{ color: 'var(--qx-text-muted)' }}>Option Leg At-Expiration Payoff Curve ($ P&L)</span>
          <span style={{ color: 'var(--qx-text-secondary)' }}>Spot Target: ${underlyingPrice}</span>
        </div>

        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto overflow-visible">
          {/* Grid lines */}
          <line x1={padding} y1={zeroY} x2={width - padding} y2={zeroY} stroke="var(--qx-border-subtle)" strokeWidth="1.5" strokeDasharray="4 4" />
          <line x1={spotX} y1={padding} x2={spotX} y2={height - padding} stroke="var(--qx-accent)" strokeWidth="1.5" strokeDasharray="3 3" />

          {/* Area fill under curve */}
          <polygon
            points={`${padding},${zeroY} ${pointsString} ${width - padding},${zeroY}`}
            fill="url(#payoffGradient)"
            opacity="0.25"
          />

          <defs>
            <linearGradient id="payoffGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--qx-positive)" stopOpacity="0.8" />
              <stop offset="100%" stopColor="var(--qx-negative)" stopOpacity="0.8" />
            </linearGradient>
          </defs>

          {/* Main Payoff Line */}
          <polyline points={pointsString} fill="none" stroke="var(--qx-positive)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />

          {/* Breakeven Dots */}
          {payoffData.breakevens?.map((be, idx) => {
            const beX = mapX(be);
            return (
              <g key={idx}>
                <circle cx={beX} cy={zeroY} r="5" fill="var(--qx-warning)" stroke="var(--qx-bg-canvas)" strokeWidth="2" />
                <text x={beX} y={zeroY - 10} textAnchor="middle" fill="var(--qx-warning)" fontSize="11" fontWeight="bold">
                  BE: ${be}
                </text>
              </g>
            );
          })}

          {/* Spot price marker */}
          <circle cx={spotX} cy={mapY(curve.find((c) => Math.abs(c.underlying_price - underlyingPrice) < 2)?.pnl_dollars || 0)} r="6" fill="var(--qx-accent)" />

          {/* X Axis Labels */}
          <text x={padding} y={height - 10} fill="var(--qx-text-muted)" fontSize="11">
            ${minPrice}
          </text>
          <text x={width / 2} y={height - 10} fill="var(--qx-text-muted)" fontSize="11" textAnchor="middle">
            Price Range (±20%)
          </text>
          <text x={width - padding} y={height - 10} fill="var(--qx-text-muted)" fontSize="11" textAnchor="end">
            ${maxPrice}
          </text>

          {/* Y Axis Zero Label */}
          <text x={padding - 8} y={zeroY + 4} fill="var(--qx-text-muted)" fontSize="10" textAnchor="end">
            $0
          </text>
        </svg>

        {/* Legend */}
        <div className="flex justify-center gap-6 mt-3 text-xs" style={{ color: 'var(--qx-text-secondary)' }}>
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full inline-block" style={{ background: 'var(--qx-positive)' }}></span> Profit Zone</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full inline-block" style={{ background: 'var(--qx-negative)' }}></span> Max Loss Risk</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full inline-block" style={{ background: 'var(--qx-warning)' }}></span> Breakeven</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full inline-block" style={{ background: 'var(--qx-accent)' }}></span> Current Spot</span>
        </div>
      </div>
    );
  };

  return (
    <section id="strategy-workspaces" className="max-w-7xl mx-auto px-4 py-8 text-slate-100 font-sans">
      {/* Section Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 text-xs font-semibold rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 uppercase tracking-wide">
              Phase 6.1 Architecture
            </span>
            <h2 className="text-2xl font-bold tracking-tight text-white">Modular Strategy Workspaces & Leg Payoff Engine</h2>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Interactive leg payoff calculator, DTE term structure evaluation, and probability risk metrics.
          </p>
        </div>

        {/* Underlying Selector */}
        <div className="mt-4 md:mt-0 flex items-center gap-3 bg-slate-900/80 p-2 rounded-lg border border-slate-800">
          <label htmlFor="strategy-underlying-symbol" className="text-xs font-medium text-slate-400">Underlying:</label>
          <input
            id="strategy-underlying-symbol"
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-16 bg-slate-950 border border-slate-700 text-slate-200 text-sm font-bold rounded px-2 py-1 uppercase text-center focus:outline-none focus:border-sky-500"
          />
          <label htmlFor="strategy-underlying-price" className="text-xs font-medium text-slate-400">Spot Price:</label>
          <input
            id="strategy-underlying-price"
            type="number"
            value={underlyingPrice}
            onChange={(e) => setUnderlyingPrice(e.target.value)}
            className="w-24 bg-slate-950 border border-slate-700 text-slate-200 text-sm font-bold rounded px-2 py-1 text-center focus:outline-none focus:border-sky-500"
          />
        </div>
      </div>

      {/* Strategy Tabs */}
      <div className="flex flex-wrap gap-2 mb-6">
        {STRATEGY_PRESETS.map((strat) => (
          <button
            key={strat.id}
            onClick={() => setActiveStrategy(strat.id)}
            className={`px-4 py-2.5 rounded-lg font-medium text-sm transition-all duration-150 flex items-center gap-2 border ${
              activeStrategy === strat.id
                ? 'bg-sky-600/20 text-sky-300 border-sky-500 shadow-md shadow-sky-950/50'
                : 'bg-slate-900/60 text-slate-400 border-slate-800 hover:bg-slate-800 hover:text-slate-200'
            }`}
          >
            <span>{strat.icon}</span>
            <span>{strat.name}</span>
          </button>
        ))}
      </div>

      {/* Workspace Banner */}
      {workspaceInfo && (
        <div className="mb-6 p-4 rounded-xl bg-slate-900/70 border border-slate-800/80 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-slate-100">{workspaceInfo.strategy_name}</h3>
              <span className="text-xs px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800">
                {workspaceInfo.category}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">{workspaceInfo.description}</p>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="text-center px-3 py-1.5 rounded bg-slate-950 border border-slate-800">
              <div className="text-slate-500">Compatibility Score</div>
              <div className="text-base font-bold text-emerald-400">{workspaceInfo.compatibility_score}%</div>
            </div>
            <div className="text-center px-3 py-1.5 rounded bg-slate-950 border border-slate-800">
              <div className="text-slate-500">Ideal IV Condition</div>
              <div className="text-xs font-semibold text-amber-400 mt-0.5">{workspaceInfo.ideal_iv_rank}</div>
            </div>
          </div>
        </div>
      )}

      {/* Main Grid: Leg Controls & Payoff Visualization */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Option Legs Table & Controls (5 Cols) */}
        <div className="lg:col-span-5 bg-slate-900/60 border border-slate-800 rounded-xl p-5 shadow-lg">
          <div className="flex justify-between items-center mb-4">
            <h4 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <span>🧩 Strategy Legs & Strike Setup</span>
            </h4>
            <button
              onClick={addLeg}
              className="text-xs px-2.5 py-1 rounded bg-sky-900/50 hover:bg-sky-800/60 text-sky-300 border border-sky-700/60 transition-colors font-medium"
            >
              + Add Leg
            </button>
          </div>

          <div className="space-y-3">
            {legs.map((leg, index) => (
              <div key={index} className="p-3 bg-slate-950/80 border border-slate-800 rounded-lg flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-sky-400">Leg #{index + 1}</span>
                  <button
                    onClick={() => removeLeg(index)}
                    className="text-slate-500 hover:text-rose-400 transition-colors font-bold px-1"
                    title="Remove Leg"
                  >
                    ✕
                  </button>
                </div>

                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <label htmlFor={`strategy-leg-${index}-action`} className="text-slate-500 block mb-0.5">Action</label>
                    <select
                      id={`strategy-leg-${index}-action`}
                      value={leg.action}
                      onChange={(e) => handleLegChange(index, 'action', e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 font-semibold focus:outline-none"
                    >
                      <option value="buy">BUY (Long)</option>
                      <option value="sell">SELL (Short)</option>
                    </select>
                  </div>

                  <div>
                    <label htmlFor={`strategy-leg-${index}-type`} className="text-slate-500 block mb-0.5">Type</label>
                    <select
                      id={`strategy-leg-${index}-type`}
                      value={leg.option_type}
                      onChange={(e) => handleLegChange(index, 'option_type', e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 font-semibold focus:outline-none"
                    >
                      <option value="call">CALL</option>
                      <option value="put">PUT</option>
                    </select>
                  </div>

                  <div>
                    <label htmlFor={`strategy-leg-${index}-strike`} className="text-slate-500 block mb-0.5">Strike ($)</label>
                    <input
                      id={`strategy-leg-${index}-strike`}
                      type="number"
                      value={leg.strike}
                      onChange={(e) => handleLegChange(index, 'strike', e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 font-bold focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <label htmlFor={`strategy-leg-${index}-premium`} className="text-slate-500 block mb-0.5">Premium ($)</label>
                    <input
                      id={`strategy-leg-${index}-premium`}
                      type="number"
                      step="0.1"
                      value={leg.premium}
                      onChange={(e) => handleLegChange(index, 'premium', e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 font-bold focus:outline-none text-emerald-400"
                    />
                  </div>

                  <div>
                    <label htmlFor={`strategy-leg-${index}-quantity`} className="text-slate-500 block mb-0.5">Quantity</label>
                    <input
                      id={`strategy-leg-${index}-quantity`}
                      type="number"
                      value={leg.quantity}
                      onChange={(e) => handleLegChange(index, 'quantity', e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 font-bold focus:outline-none"
                    />
                  </div>

                  <div>
                    <label htmlFor={`strategy-leg-${index}-dte`} className="text-slate-500 block mb-0.5">DTE</label>
                    <input
                      id={`strategy-leg-${index}-dte`}
                      type="number"
                      value={leg.dte}
                      onChange={(e) => handleLegChange(index, 'dte', e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-slate-200 font-bold focus:outline-none"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Dynamic Payoff Diagram & Financial Metrics (7 Cols) */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          {/* Key Metrics Cards */}
          {payoffData && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center">
                <span className="text-xs text-slate-400 uppercase font-semibold">Net Cost / Credit</span>
                <div className={`text-lg font-bold mt-1 ${payoffData.net_debit_credit > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {payoffData.net_debit_credit > 0 ? `$${payoffData.net_debit_credit} Debit` : `$${Math.abs(payoffData.net_debit_credit)} Credit`}
                </div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center">
                <span className="text-xs text-slate-400 uppercase font-semibold">Max Risk</span>
                <div className="text-lg font-bold text-rose-400 mt-1">${payoffData.max_risk_dollars}</div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center">
                <span className="text-xs text-slate-400 uppercase font-semibold">Max Profit</span>
                <div className="text-lg font-bold text-emerald-400 mt-1">
                  {payoffData.max_profit_dollars !== null ? `$${payoffData.max_profit_dollars}` : 'Unlimited'}
                </div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center">
                <span className="text-xs text-slate-400 uppercase font-semibold">Breakeven(s)</span>
                <div className="text-sm font-bold text-sky-300 mt-1.5">
                  {payoffData.breakevens?.length > 0 ? payoffData.breakevens.map((b) => `$${b}`).join(' | ') : 'N/A'}
                </div>
              </div>
            </div>
          )}

          {/* SVG Payoff Curve */}
          {renderPayoffSvg()}
        </div>
      </div>
    </section>
  );
}
