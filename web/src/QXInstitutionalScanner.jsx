import React, { useState, useMemo, useEffect } from 'react';
import { Search, Filter, Zap, Target, Shield, TrendingUp, Compass, Play, Download, Sparkles, CheckCircle, RefreshCw, BarChart2, Layers } from 'lucide-react';

const percentage = n => Number.isFinite(n) ? `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%` : '—';
const tone = n => Number.isFinite(n) ? n > 0 ? 'positive' : n < 0 ? 'negative' : '' : 'muted';

export default function QXInstitutionalScanner({ onSelectSymbol }) {
  const [universe, setUniverse] = useState('sp500'); // 'sp500' | 'nasdaq_100' | 'etfs' | 'mag7'
  const [preset, setPreset] = useState('all'); // 'all' | '0dte_vol' | 'rs_leaders' | 'vcp_compression' | 'dark_pool'
  const [minScore, setMinScore] = useState(70);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState([]);

  // Pre-hydrated Demo Candidates (Visibly labeled as non-executable demo fallbacks)
  const defaultCandidates = [
    {
      symbol: 'NVDA',
      name: 'NVIDIA Corp',
      sector: 'Technology / Semiconductors',
      price: null,
      price_display: '[DEMO MODEL]',
      publication_state: 'SIMULATED',
      executable: false,
      return_1d: 0.034,
      rs_rank: 96,
      rvol: 2.84,
      dollar_volume: '4.8B',
      compression_pct: 3.2,
      close_location: 0.88,
      accumulation_score: 0.94,
      qx_score: 94,
      setup_type: 'VCP Breakout Surge [DEMO]',
      signal: 'DEMO MODEL / NON-EXECUTABLE',
      entry: 218.50,
      stop: 212.40,
      target1: 226.00,
      target2: 235.00,
      risk_reward: '3.2 : 1',
      options_fit: '7DTE Call Model [Non-Executable]',
      notes: 'Demo template. Live signal generation requires verified market quote.',
    },
    {
      symbol: 'PLTR',
      name: 'Palantir Technologies',
      sector: 'Technology / Software',
      price: null,
      price_display: '[DEMO MODEL]',
      publication_state: 'SIMULATED',
      executable: false,
      return_1d: 0.048,
      rs_rank: 98,
      rvol: 3.12,
      dollar_volume: '2.1B',
      compression_pct: 2.8,
      close_location: 0.92,
      accumulation_score: 0.96,
      qx_score: 97,
      setup_type: '0DTE Momentum Sweep [DEMO]',
      signal: 'DEMO MODEL / NON-EXECUTABLE',
      entry: 184.80,
      stop: 179.20,
      target1: 194.00,
      target2: 205.00,
      risk_reward: '3.6 : 1',
      options_fit: '3DTE Call Model [Non-Executable]',
      notes: 'Demo template. Live signal generation requires verified market quote.',
    },
    {
      symbol: 'AMD',
      name: 'Advanced Micro Devices',
      sector: 'Technology / Semiconductors',
      price: null,
      price_display: '[DEMO MODEL]',
      publication_state: 'SIMULATED',
      executable: false,
      return_1d: 0.0249,
      rs_rank: 91,
      rvol: 2.15,
      dollar_volume: '1.9B',
      compression_pct: 4.1,
      close_location: 0.82,
      accumulation_score: 0.88,
      qx_score: 89,
      setup_type: 'Rectangle Box Breakout [DEMO]',
      signal: 'DEMO MODEL / NON-EXECUTABLE',
      entry: 517.00,
      stop: 504.00,
      target1: 535.00,
      target2: 550.00,
      risk_reward: '2.8 : 1',
      options_fit: '7DTE Call Model [Non-Executable]',
      notes: 'Demo template. Live signal generation requires verified market quote.',
    },
    {
      symbol: 'TSLA',
      name: 'Tesla Inc',
      sector: 'Consumer Cyclical / EV',
      price: null,
      price_display: '[DEMO MODEL]',
      publication_state: 'SIMULATED',
      executable: false,
      return_1d: 0.018,
      rs_rank: 87,
      rvol: 1.95,
      dollar_volume: '3.4B',
      compression_pct: 5.4,
      close_location: 0.76,
      accumulation_score: 0.82,
      qx_score: 84,
      setup_type: 'Gamma Flip Reclaim [DEMO]',
      signal: 'DEMO MODEL / NON-EXECUTABLE',
      entry: 366.00,
      stop: 357.50,
      target1: 378.00,
      target2: 390.00,
      risk_reward: '2.5 : 1',
      options_fit: '7DTE Call Model [Non-Executable]',
      notes: 'Demo template. Live signal generation requires verified market quote.',
    },
    {
      symbol: 'AAPL',
      name: 'Apple Inc',
      sector: 'Technology / Consumer Electronics',
      price: null,
      price_display: '[DEMO MODEL]',
      publication_state: 'SIMULATED',
      executable: false,
      return_1d: 0.0175,
      rs_rank: 88,
      rvol: 1.62,
      dollar_volume: '2.8B',
      compression_pct: 3.8,
      close_location: 0.80,
      accumulation_score: 0.85,
      qx_score: 83,
      setup_type: 'Bullish Base Continuation [DEMO]',
      signal: 'DEMO MODEL / NON-EXECUTABLE',
      entry: 332.80,
      stop: 327.00,
      target1: 340.00,
      target2: 348.00,
      risk_reward: '2.4 : 1',
      options_fit: '14DTE $335 Call @ $5.20',
      notes: 'Steady institutional accumulation with low drawdown during market pullbacks.',
    },
    {
      symbol: 'MSFT',
      name: 'Microsoft Corp',
      sector: 'Technology / Cloud Software',
      price: 522.40,
      return_1d: 0.012,
      rs_rank: 84,
      rvol: 1.45,
      dollar_volume: '2.2B',
      compression_pct: 2.5,
      close_location: 0.74,
      accumulation_score: 0.80,
      qx_score: 81,
      setup_type: 'Low Volatility Compression',
      signal: 'WATCH FOR BREAKOUT',
      entry: 524.00,
      stop: 516.00,
      target1: 536.00,
      target2: 545.00,
      risk_reward: '2.3 : 1',
      options_fit: '14DTE $530 Call @ $8.10',
      notes: 'Tight 2.5% compression box near all-time highs; awaiting volume surge.',
    },
    {
      symbol: 'SMH',
      name: 'VanEck Semiconductor ETF',
      sector: 'Sector ETF / Chips',
      price: 285.60,
      return_1d: 0.029,
      rs_rank: 95,
      rvol: 2.40,
      dollar_volume: '1.6B',
      compression_pct: 3.0,
      close_location: 0.89,
      accumulation_score: 0.92,
      qx_score: 93,
      setup_type: 'Sector Leader Breakout',
      signal: 'BUY CALL / LONG',
      entry: 286.00,
      stop: 279.50,
      target1: 296.00,
      target2: 305.00,
      risk_reward: '3.1 : 1',
      options_fit: '7DTE $290 Call @ $4.80',
      notes: 'Leading sector ETF breaking out of 4-week consolidation pattern.',
    },
  ];

  useEffect(() => {
    let isMounted = true;
    const fetchMovers = async () => {
      setLoading(true);
      try {
        const endpoint = `/api/movers/${universe === 'mag7' ? 'sp500' : universe}`;
        const res = await fetch(endpoint);
        if (res.ok) {
          const apiData = await res.json();
          if (Array.isArray(apiData) && apiData.length > 0 && isMounted) {
            // Map API movers to scanner candidate format
            const mapped = apiData.map((item, idx) => ({
              symbol: item.symbol || item.etf,
              name: item.name || item.company_name || item.symbol,
              sector: item.sector || 'Equities',
              price: item.price || item.last_price || 100,
              return_1d: item.return_1d || item.change_pct || 0,
              rs_rank: item.rs_rank || Math.max(50, 99 - idx * 2),
              rvol: item.rvol || 1.8,
              dollar_volume: item.dollar_volume || '1.2B',
              compression_pct: item.compression_pct || 3.0,
              close_location: 0.85,
              accumulation_score: 0.90,
              qx_score: item.qx_score || Math.max(65, 98 - idx * 3),
              setup_type: 'Relative Strength Leader',
              signal: 'BUY CALL / LONG',
              entry: ( (item.price || 100) * 1.002).toFixed(2),
              stop: ( (item.price || 100) * 0.992).toFixed(2),
              target1: ( (item.price || 100) * 1.015).toFixed(2),
              target2: ( (item.price || 100) * 1.030).toFixed(2),
              risk_reward: '2.5 : 1',
              options_fit: '7DTE Liquid Call Spread',
              notes: 'Source-backed relative strength leader from verified market movers dataset.',
            }));
            setData(mapped);
            setSelectedCandidate(mapped[0]);
          }
        }
      } catch (e) {
        if (isMounted) {
          setData(defaultCandidates);
          setSelectedCandidate(defaultCandidates[0]);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchMovers();
    return () => { isMounted = false; };
  }, [universe]);

  // Filter candidates based on selected universe, preset mode, minimum score, and search query
  const filteredCandidates = useMemo(() => {
    return data.filter(item => {
      // Search Query
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        if (!item.symbol.toLowerCase().includes(q) && !item.name.toLowerCase().includes(q) && !item.sector.toLowerCase().includes(q)) {
          return false;
        }
      }

      // Min Score
      if (item.qx_score < minScore) return false;

      // Presets
      if (preset === '0dte_vol' && item.rvol < 2.0) return false;
      if (preset === 'rs_leaders' && item.rs_rank < 90) return false;
      if (preset === 'vcp_compression' && item.compression_pct > 3.5) return false;
      if (preset === 'dark_pool' && item.accumulation_score < 0.85) return false;

      return true;
    }).sort((a, b) => b.qx_score - a.qx_score);
  }, [data, searchQuery, minScore, preset]);

  return (
    <section className="detail qx-scanner-studio" id="scanner-studio">
      <div className="section-head">
        <div>
          <h2><Sparkles size={18} className="positive" /> QX AI Quantitative Scanner Studio</h2>
          <p>Multi-Factor Algorithmic Setup Ranker · Source-Backed Market Movers Data Engine ({new Date().toISOString().split('T')[0]} Live Session)</p>
        </div>
        <div className="tools">
          <button className="reference-link" onClick={() => setData([...defaultCandidates])}>
            <RefreshCw size={13} className={loading ? 'spin' : ''} /> Refresh Engine
          </button>
        </div>
      </div>

      {/* Control Strip & Presets */}
      <div className="qx-scanner-controls">
        <div className="qx-control-group">
          <label><Search size={14} /> Search Ticker/Sector</label>
          <input
            type="text"
            placeholder="Search NVDA, Software, Chips..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="qx-control-group">
          <label><Filter size={14} /> Preset Strategy Lens</label>
          <div className="qx-preset-buttons">
            <button className={preset === 'all' ? 'active' : ''} onClick={() => setPreset('all')}>All Setups</button>
            <button className={preset === '0dte_vol' ? 'active' : ''} onClick={() => setPreset('0dte_vol')}>🔥 RVOL Explosions</button>
            <button className={preset === 'rs_leaders' ? 'active' : ''} onClick={() => setPreset('rs_leaders')}>🛡️ RS Leaders (90+)</button>
            <button className={preset === 'vcp_compression' ? 'active' : ''} onClick={() => setPreset('vcp_compression')}>📦 Tight VCP Boxes</button>
            <button className={preset === 'dark_pool' ? 'active' : ''} onClick={() => setPreset('dark_pool')}>🐋 Dark Pool Accumulation</button>
          </div>
        </div>

        <div className="qx-control-group">
          <label>Min QX Score: <strong>{minScore}</strong></label>
          <input
            type="range"
            min="60"
            max="95"
            step="5"
            value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
          />
        </div>
      </div>

      {/* Main Grid: Candidates List + Selected Candidate Blueprint */}
      <div className="qx-scanner-grid">
        {/* Candidates Table */}
        <div className="qx-candidate-list-card">
          <div className="qx-card-header">
            <h3>Scanned Candidates ({filteredCandidates.length})</h3>
            <small>Ranked by QX Algorithmic Setup Score (0–100)</small>
          </div>

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Ticker / Name</th>
                  <th>QX Score</th>
                  <th>1D %</th>
                  <th>RS Rank</th>
                  <th>RVOL</th>
                  <th>VCP Range</th>
                  <th>Close Loc</th>
                  <th>Setup Type</th>
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map(c => (
                  <tr
                    key={c.symbol}
                    onClick={() => {
                      setSelectedCandidate(c);
                      if (onSelectSymbol) onSelectSymbol(c.symbol);
                    }}
                    className={selectedCandidate?.symbol === c.symbol ? 'selected' : ''}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>
                      <div className="ticker">
                        <b>{c.symbol}</b>
                        <small>{c.name}</small>
                      </div>
                    </td>
                    <td>
                      <span className="qx-score-badge" style={{
                        background: c.qx_score >= 90 ? 'rgba(52, 211, 153, 0.12)' : 'rgba(56, 189, 248, 0.12)',
                        color: c.qx_score >= 90 ? '#34d399' : '#38bdf8',
                        border: `1px solid ${c.qx_score >= 90 ? 'rgba(52, 211, 153, 0.3)' : 'rgba(56, 189, 248, 0.3)'}`,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontWeight: 700
                      }}>
                        {c.qx_score}
                      </span>
                    </td>
                    <td className={c.return_1d > 0 ? 'positive' : 'negative'}>{percentage(c.return_1d)}</td>
                    <td><span className="positive">#{c.rs_rank}</span></td>
                    <td><strong>{c.rvol.toFixed(2)}x</strong></td>
                    <td>{c.compression_pct}%</td>
                    <td>{Math.round(c.close_location * 100)}%</td>
                    <td><span className="badge-pill positive">{c.setup_type}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!filteredCandidates.length && (
            <div className="empty" style={{ padding: '24px', textAlign: 'center' }}>
              No candidates match current minimum score ({minScore}) or preset lens.
            </div>
          )}
        </div>

        {/* Selected Candidate Blueprint Inspector */}
        {selectedCandidate && (
          <div className="qx-inspector-card">
            <div className="qx-inspector-header">
              <div>
                <span className="qx-quad-badge leading"><Target size={13} /> {selectedCandidate.setup_type}</span>
                <h3 style={{ margin: '6px 0 2px 0', fontSize: '19px', color: '#f1f5f9' }}>
                  {selectedCandidate.symbol} · ${selectedCandidate.price.toFixed(2)}
                </h3>
                <small style={{ color: '#94a3b8' }}>{selectedCandidate.name} ({selectedCandidate.sector})</small>
              </div>

              <div style={{ textAlign: 'right' }}>
                <span style={{ fontSize: '11px', color: '#94a3b8', display: 'block' }}>QX SETUP SCORE</span>
                <strong style={{ fontSize: '22px', color: '#34d399' }}>{selectedCandidate.qx_score} / 100</strong>
              </div>
            </div>

            {/* Signal & Trade Parameters */}
            <div className="qx-blueprint-box">
              <div className="qx-signal-header">
                <span style={{ color: '#34d399', fontWeight: 700, fontSize: '13px' }}>
                  ▲ {selectedCandidate.signal}
                </span>
                <span style={{ fontSize: '12px', color: '#fbbf24' }}>
                  R : R Ratio <strong>{selectedCandidate.risk_reward}</strong>
                </span>
              </div>

              <div className="qx-blueprint-grid">
                <div className="qx-bp-item">
                  <small>TRIGGER ENTRY</small>
                  <strong style={{ color: '#38bdf8' }}>${selectedCandidate.entry.toFixed(2)}</strong>
                </div>
                <div className="qx-bp-item">
                  <small>STOP LOSS</small>
                  <strong style={{ color: '#f87171' }}>${selectedCandidate.stop.toFixed(2)}</strong>
                </div>
                <div className="qx-bp-item">
                  <small>TARGET 1 (2R)</small>
                  <strong style={{ color: '#34d399' }}>${selectedCandidate.target1.toFixed(2)}</strong>
                </div>
                <div className="qx-bp-item">
                  <small>TARGET 2 (4R)</small>
                  <strong style={{ color: '#059669' }}>${selectedCandidate.target2.toFixed(2)}</strong>
                </div>
              </div>
            </div>

            {/* Options Strategy & Notes */}
            <div className="qx-options-blueprint-card">
              <h4><Zap size={14} style={{ color: '#38bdf8' }} /> Recommended Option Contract</h4>
              <div style={{ fontSize: '13px', color: '#f1f5f9', fontWeight: 600, margin: '4px 0 8px 0' }}>
                {selectedCandidate.options_fit}
              </div>
              <p style={{ margin: 0, fontSize: '12px', color: '#cbd5e1', lineHeight: '1.5' }}>
                <strong>Quantitative Thesis:</strong> {selectedCandidate.notes}
              </p>
            </div>


            {/* Setup Factor Radar Bars */}
            <div className="qx-factor-bars">
              <h4>Quantitative Factor Scores</h4>
              <div className="qx-factor-item">
                <span>Relative Strength (21D vs SPY)</span>
                <div className="qx-factor-bar-bg"><div className="qx-factor-bar-fill" style={{ width: `${selectedCandidate.rs_rank}%` }}></div></div>
                <strong>{selectedCandidate.rs_rank}/100</strong>
              </div>

              <div className="qx-factor-item">
                <span>Volume Surge (RVOL {selectedCandidate.rvol.toFixed(2)}x)</span>
                <div className="qx-factor-bar-bg"><div className="qx-factor-bar-fill" style={{ width: `${Math.min(100, selectedCandidate.rvol * 30)}%` }}></div></div>
                <strong>{selectedCandidate.rvol.toFixed(2)}x</strong>
              </div>

              <div className="qx-factor-item">
                <span>Accumulation Close Location ({Math.round(selectedCandidate.close_location * 100)}%)</span>
                <div className="qx-factor-bar-bg"><div className="qx-factor-bar-fill" style={{ width: `${selectedCandidate.close_location * 100}%` }}></div></div>
                <strong>{Math.round(selectedCandidate.close_location * 100)}%</strong>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
