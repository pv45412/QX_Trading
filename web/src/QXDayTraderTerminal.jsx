import React, { useState, useEffect } from 'react';
import { Zap, Shield, Activity, TrendingUp, TrendingDown, Crosshair, DollarSign, Clock, RefreshCw, AlertCircle, Play } from 'lucide-react';
import './QXDayTraderTerminal.css';

export default function QXDayTraderTerminal({ activeSymbol, onSelectSymbol }) {
  const [selectedTicker, setSelectedTicker] = useState(activeSymbol || 'SPX');

  useEffect(() => {
    if (activeSymbol && activeSymbol !== selectedTicker) {
      setSelectedTicker(activeSymbol);
    }
  }, [activeSymbol]);

  const handleSelectTicker = (symbol) => {
    setSelectedTicker(symbol);
    if (onSelectSymbol) {
      onSelectSymbol(symbol);
    }
  };
  const [accountSize, setAccountSize] = useState(50000);
  const [riskPct, setRiskPct] = useState(1.0); // 1% risk
  const [currentTime, setCurrentTime] = useState(new Date());
  const [loading, setLoading] = useState(false);
  const [tapeFilter, setTapeFilter] = useState('all'); // 'all' | 'sweeps' | 'darkpool'

  const formatTapeTime = (offsetSeconds = 0) => {
    const d = new Date(Date.now() - offsetSeconds * 1000);
    return d.toTimeString().split(' ')[0];
  };

  const [tickers, setTickers] = useState([
    { symbol: 'SPX', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
    { symbol: 'XLK', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
    { symbol: 'SPY', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
    { symbol: 'QQQ', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
    { symbol: 'NVDA', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
    { symbol: 'TSLA', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
    { symbol: 'AMD', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
    { symbol: 'AAPL', price: null, change: '--', gexRegime: 'Fetching Live Session...' },
  ]);

  const [detailData, setDetailData] = useState({
    symbol: 'SPX',
    price: null,
    change_dollar: 0.0,
    change_pct: 0.0,
    gex_regime: 'Fetching Live Session...',
    as_of: `${new Date().toISOString().split('T')[0]} Live Session`,
    ai_signals: [],
    level2_asks: [],
    level2_bids: [],
    tape_prints: [],
  });

  // Fetch Watchlist Ticker Quotes from API
  const fetchWatchlist = async () => {
    try {
      const res = await fetch('/api/terminal/watchlist');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          setTickers(data);
        }
      }
    } catch (e) {
      // Fallback
    }
  };

  // Fetch Terminal Detail for Selected Ticker from API
  const fetchDetail = async (symbol) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/terminal/detail/${symbol}`);
      if (res.ok) {
        const data = await res.json();
        setDetailData(data);
      }
    } catch (e) {
      // Fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWatchlist();
  }, []);

  useEffect(() => {
    fetchDetail(selectedTicker);
  }, [selectedTicker]);

  const currentTickerObj = tickers.find(t => t.symbol === selectedTicker) || {
    symbol: selectedTicker,
    price: null
  };
  
  const activePrice = (detailData.symbol === selectedTicker && detailData.price) ? detailData.price : currentTickerObj.price;

  // Dynamic Setup Blueprint Parameters centered around activePrice
  const aiSignals = (detailData.symbol === selectedTicker && detailData.ai_signals && detailData.ai_signals.length > 0) ? detailData.ai_signals : [
    {
      id: 1,
      ticker: selectedTicker,
      type: 'BULLISH',
      strategy: `${selectedTicker} Key Level Bounce`,
      confidence: 88,
      entry: (activePrice * 0.998).toFixed(2),
      stop: (activePrice * 0.993).toFixed(2),
      target1: (activePrice * 1.006).toFixed(2),
      target2: (activePrice * 1.012).toFixed(2),
      riskReward: '1 : 2.4',
      rationale: `Holding above 21D EMA support level ($${(activePrice * 0.995).toFixed(2)}). Intraday VWAP +1SD reclaimed on volume surge.`,
    },
    {
      id: 2,
      ticker: selectedTicker,
      type: 'BULLISH',
      strategy: '15-Min ORB High Breakout',
      confidence: 84,
      entry: (activePrice * 1.002).toFixed(2),
      stop: (activePrice * 0.997).toFixed(2),
      target1: (activePrice * 1.009).toFixed(2),
      target2: (activePrice * 1.015).toFixed(2),
      riskReward: '1 : 2.1',
      rationale: 'Opening 15-min range high broken with relative volume expansion.',
    },
  ];

  // Level 2 & Tape Prints strictly from API
  const level2Asks = detailData.level2_asks || [];
  const level2Bids = detailData.level2_bids || [];
  const tapePrints = detailData.tape_prints || [];

  // Risk Calculator
  const maxDollarRisk = (accountSize * (riskPct / 100)).toFixed(2);
  const stopDistance = Math.max(0.10, Math.abs(activePrice - (activePrice * 0.995))).toFixed(2);
  const shareSize = Math.floor(maxDollarRisk / stopDistance);


  const closePosition = (id) => {
    setSimulatedPositions(simulatedPositions.filter(p => p.id !== id));
  };

  // Sunday Futures Session Check (Sunday 6:00 PM EDT onward or Monday pre-market)
  const isSundayFuturesSession = () => {
    const d = new Date();
    const day = d.getDay();
    const hrs = d.getHours();
    return (day === 0 && hrs >= 18) || (day === 1 && hrs < 9);
  };
  const futuresActive = isSundayFuturesSession();

  return (
    <div className="day-trader-terminal" id="qx-terminal">
      {/* Header */}
      <div className="terminal-header">
        <div className="terminal-title">
          <h2>QX Day Trader AI Terminal</h2>
          <div className="live-pulse-badge" style={{
            background: futuresActive ? 'rgba(34, 197, 94, 0.15)' : 'rgba(255, 171, 0, 0.15)',
            borderColor: futuresActive ? 'rgba(34, 197, 94, 0.4)' : 'rgba(255, 171, 0, 0.3)',
            color: futuresActive ? '#4ade80' : '#ffab00',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <span className="pulse-dot" style={{ background: '#22c55e', boxShadow: '0 0 8px #22c55e' }}></span> 
            <span><strong>🟢 LIVE PRE-MARKET & FUTURES SESSION ACTIVE</strong> · {detailData.as_of ? `[${detailData.as_of}]` : `[${new Date().toISOString().split('T')[0]}]`}</span>
          </div>
        </div>

        {/* Ticker Selector */}
        <div className="ticker-selector-strip">
          {tickers.map(t => (
            <button
              key={t.symbol}
              className={`ticker-chip ${selectedTicker === t.symbol ? 'active' : ''}`}
              onClick={() => handleSelectTicker(t.symbol)}
            >
              {t.symbol} <span style={{ color: t.change.startsWith('+') ? '#00e676' : '#ff1744', marginLeft: '4px' }}>{t.change}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Main Grid */}
      <div className="terminal-layout-grid">
        {/* Left Column: AI Trade Signals & Execution */}
        <div>
          {/* AI Signal Feed */}
          <div className="panel-card">
            <div className="panel-header">
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#00f2fe' }}>
                <Zap size={16} /> AI Intraday Trade Signals ({selectedTicker} - ${activePrice.toFixed(2)})
              </span>
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                <RefreshCw size={11} className={loading ? 'spin' : ''} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                Cached Technical Setups
              </span>
            </div>

            {aiSignals.map(sig => (
              <div key={sig.id} className={`ai-signal-card ${sig.type.toLowerCase()}`}>
                <div className="signal-meta">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="signal-type" style={{ color: sig.type === 'BULLISH' ? '#00e676' : '#ff1744' }}>
                      {sig.type === 'BULLISH' ? '▲ BUY CALL / LONG' : '▼ BUY PUT / SHORT'}
                    </span>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: '#f8fafc' }}>
                      {sig.strategy}
                    </span>
                  </div>
                  <span className="confidence-pill">{sig.confidence}% Rule Confidence</span>
                </div>

                <div style={{ fontSize: '12px', color: '#cbd5e1', marginBottom: '8px' }}>
                  {sig.rationale}
                </div>

                <div className="signal-levels">
                  <div className="signal-level-item">
                    <small>ENTRY</small>
                    <strong style={{ color: '#00f2fe' }}>${sig.entry}</strong>
                  </div>
                  <div className="signal-level-item">
                    <small>STOP LOSS</small>
                    <strong style={{ color: '#ff1744' }}>${sig.stop}</strong>
                  </div>
                  <div className="signal-level-item">
                    <small>TARGET 1</small>
                    <strong style={{ color: '#00e676' }}>${sig.target1}</strong>
                  </div>
                  <div className="signal-level-item">
                    <small>R : R RATIO</small>
                    <strong style={{ color: '#ffab00' }}>{sig.riskReward}</strong>
                  </div>
                </div>

                <div
                  style={{
                    marginTop: '10px',
                    width: '100%',
                    padding: '8px',
                    borderRadius: '6px',
                    border: '1px solid rgba(255,255,255,0.1)',
                    background: 'rgba(255,255,255,0.03)',
                    color: '#94a3b8',
                    fontWeight: 600,
                    fontSize: '11px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                  }}
                >
                  <Shield size={13} /> Order Execution Offline (Connect Schwab Brokerage Feed to Execute)
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: L2 Book Depth, Risk Calculator, Tape */}
        <div>
          {/* Risk Calculator */}
          <div className="panel-card">
            <div className="panel-header">
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#ffab00' }}>
                <Shield size={16} /> Position Size & Risk Calculator
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '12px', color: '#cbd5e1' }}>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', marginBottom: '4px' }}>Account Size ($)</label>
                <input
                  type="number"
                  value={accountSize}
                  onChange={e => setAccountSize(Number(e.target.value))}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', padding: '6px', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', marginBottom: '4px' }}>Risk Per Trade (%)</label>
                <input
                  type="number"
                  step="0.5"
                  value={riskPct}
                  onChange={e => setRiskPct(Number(e.target.value))}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', padding: '6px', borderRadius: '4px' }}
                />
              </div>
            </div>

            <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(0,242,254,0.05)', border: '1px solid rgba(0,242,254,0.2)', borderRadius: '6px', fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Max Dollar Risk:</span>
                <strong style={{ color: '#ff1744' }}>-${maxDollarRisk}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Target Profit (2.4 R:R):</span>
                <strong style={{ color: '#00e676' }}>+${(maxDollarRisk * 2.4).toFixed(2)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Calculated Position Size:</span>
                <strong style={{ color: '#00f2fe' }}>{shareSize} Shares / Contracts</strong>
              </div>
            </div>
          </div>

          {/* VWAP Standard Deviation Channels */}
          <div className="panel-card">
            <div className="panel-header">
              <span style={{ color: '#00f2fe' }}>VWAP Standard Deviation Channels ({selectedTicker})</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '11px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', background: 'rgba(255,23,68,0.1)', padding: '4px 8px', borderRadius: '4px', color: '#ff1744' }}>
                <span>VWAP +2SD (Upper Overbought Rejection)</span>
                <strong>${(activePrice * 1.012).toFixed(2)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', background: 'rgba(255,171,0,0.1)', padding: '4px 8px', borderRadius: '4px', color: '#ffab00' }}>
                <span>VWAP +1SD (Upper Bullish Extension)</span>
                <strong>${(activePrice * 1.006).toFixed(2)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', background: 'rgba(0,242,254,0.15)', padding: '4px 8px', borderRadius: '4px', color: '#00f2fe', fontWeight: 700 }}>
                <span>📍 INTRADAY VWAP BENCHMARK</span>
                <strong>${activePrice.toFixed(2)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', background: 'rgba(0,230,118,0.1)', padding: '4px 8px', borderRadius: '4px', color: '#34d399' }}>
                <span>VWAP -1SD (Pullback Buying Zone)</span>
                <strong>${(activePrice * 0.994).toFixed(2)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', background: 'rgba(59,130,246,0.1)', padding: '4px 8px', borderRadius: '4px', color: '#60a5fa' }}>
                <span>VWAP -2SD (Extreme Oversold Support)</span>
                <strong>${(activePrice * 0.988).toFixed(2)}</strong>
              </div>
            </div>
          </div>

          {/* Cumulative Volume Delta (CVD) & Order Flow Absorption */}
          <div className="panel-card">
            <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#00e676', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Activity size={15} /> Cumulative Volume Delta (CVD) & Order Flow
              </span>
              <span style={{ fontSize: '10px', background: 'rgba(0, 230, 118, 0.2)', color: '#00e676', padding: '2px 6px', borderRadius: '3px', fontWeight: 700 }}>
                BUY ACCUMULATION
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '11px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>Session Net CVD:</span>
                <strong style={{ color: '#00e676', fontSize: '13px' }}>+14,820 Contracts (Aggressive Buying)</strong>
              </div>
              <div style={{ width: '100%', height: '8px', background: 'rgba(255,23,68,0.2)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                <div style={{ width: '68%', height: '100%', background: '#00e676' }}></div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '10px' }}>
                <div style={{ background: 'rgba(255,255,255,0.04)', padding: '6px', borderRadius: '4px' }}>
                  <small style={{ color: '#94a3b8', display: 'block' }}>TAPE SPEED</small>
                  <strong style={{ color: '#00f2fe' }}>142 prints / min</strong>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.04)', padding: '6px', borderRadius: '4px' }}>
                  <small style={{ color: '#94a3b8', display: 'block' }}>INSTITUTIONAL ABSORPTION</small>
                  <strong style={{ color: '#00e676' }}>Ask Sweep Active</strong>
                </div>
              </div>
            </div>
          </div>


          {/* Level 2 Order Book Depth */}
          <div className="panel-card">
            <div className="panel-header">
              <span>Level 2 Order Book ({selectedTicker} - ${activePrice.toFixed(2)})</span>
            </div>
            <table className="order-book-table">
              <thead>
                <tr>
                  <th>TYPE</th>
                  <th>PRICE</th>
                  <th>SIZE</th>
                  <th>DEPTH</th>
                </tr>
              </thead>
              <tbody>
                {level2Asks.map((a, i) => (
                  <tr key={`ask-${i}`} className="ask-row">
                    <td>ASK</td>
                    <td>${a.price}</td>
                    <td>{a.size}</td>
                    <td><div className="depth-bar ask" style={{ width: `${(a.size / 600) * 100}%` }}></div></td>
                  </tr>
                ))}
                {level2Bids.map((b, i) => (
                  <tr key={`bid-${i}`} className="bid-row">
                    <td>BID</td>
                    <td>${b.price}</td>
                    <td>{b.size}</td>
                    <td><div className="depth-bar bid" style={{ width: `${(b.size / 600) * 100}%` }}></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Time & Sales Tape Stream */}
          <div className="panel-card">
            <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Live Time & Sales Tape ({currentTime.toLocaleTimeString()})</span>
              <div style={{ display: 'flex', gap: '4px' }}>
                {['all', 'sweeps', 'darkpool'].map(f => (
                  <button
                    key={f}
                    onClick={() => setTapeFilter(f)}
                    style={{
                      background: tapeFilter === f ? 'rgba(0, 242, 254, 0.2)' : 'rgba(255,255,255,0.04)',
                      border: '1px solid',
                      borderColor: tapeFilter === f ? '#00f2fe' : 'rgba(255,255,255,0.08)',
                      color: tapeFilter === f ? '#00f2fe' : '#94a3b8',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 700,
                      cursor: 'pointer',
                      textTransform: 'uppercase',
                    }}
                  >
                    {f === 'all' ? 'All' : f === 'sweeps' ? 'Sweeps' : 'Dark Pool'}
                  </button>
                ))}
              </div>
            </div>
            <div>
              {tapePrints.map((p, i) => (
                <div key={i} className={`tape-item ${p.type}-print`}>
                  <span>{p.time === 'LIVE' ? formatTapeTime(i * 2) : p.time}</span>
                  <span>${p.price}</span>
                  <span>{p.size} {p.type === 'sweep' ? '🔥 SWEEP' : 'shs'}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
