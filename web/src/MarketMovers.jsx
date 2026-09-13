import React, { useState, useMemo } from 'react';
import { groupMovers } from './movers-utils';
import { TrendingUp, TrendingDown, Filter, Zap } from 'lucide-react';

const pct = value => `${value>0?'+':''}${(value*100).toFixed(2)}%`;

export default function MarketMovers({ data, onSelect, title = 'ETF Market Movers', subtitle = 'Sector & industry ETFs' }) {
  const [minChange, setMinChange] = useState('all'); // 'all' | '1pct' | '2pct'
  const groups = groupMovers(data?.rows || [], data?.benchmark_metrics?.as_of);

  const filterFn = row => {
    if (minChange === '1pct') return Math.abs(row.return_1d) >= 0.01;
    if (minChange === '2pct') return Math.abs(row.return_1d) >= 0.02;
    return true;
  };

  const filteredGainers = useMemo(() => groups.gainers.filter(filterFn), [groups.gainers, minChange]);
  const filteredLosers = useMemo(() => groups.losers.filter(filterFn), [groups.losers, minChange]);

  const totalActive = groups.gainers.length + groups.losers.length;
  const gainerPct = totalActive ? Math.round((groups.gainers.length / totalActive) * 100) : 50;

  return (
    <section id="movers" className="market-movers">
      <div className="section-head">
        <div>
          <h2>{title}</h2>
          <p>{subtitle} · daily close-to-close · {data?.benchmark_metrics?.as_of?.slice(0,10) || 'Date unavailable'}</p>
        </div>
        <div className="tools">
          <div className="qx-filter-group">
            <span className="qx-filter-label"><Filter size={12}/> Threshold:</span>
            <button className={minChange === 'all' ? 'active' : ''} onClick={() => setMinChange('all')}>All</button>
            <button className={minChange === '1pct' ? 'active' : ''} onClick={() => setMinChange('1pct')}>&gt; 1%</button>
            <button className={minChange === '2pct' ? 'active' : ''} onClick={() => setMinChange('2pct')}>&gt; 2%</button>
          </div>
        </div>
      </div>

      <div className="qx-mover-summary-strip">
        <div className="qx-breadth-stat">
          <span>Gainers: <strong>{groups.gainers.length}</strong> ({gainerPct}%)</span>
          <span>Losers: <strong>{groups.losers.length}</strong> ({100 - gainerPct}%)</span>
          <span>Unchanged: <strong>{groups.unchanged}</strong></span>
        </div>
        <div className="mover-breadth" role="img" aria-label={`${groups.gainers.length} gainers, ${groups.losers.length} losers`}>
          <span style={{ flex: groups.gainers.length || 1 }} className="breadth-up"/>
          <span style={{ flex: groups.unchanged }} className="breadth-flat"/>
          <span style={{ flex: groups.losers.length || 1 }} className="breadth-down"/>
        </div>
      </div>

      <div className="mover-columns">
        {[['Top Gainers', filteredGainers, TrendingUp, 'positive'], ['Top Losers', filteredLosers, TrendingDown, 'negative']].map(([label, rows, Icon, toneClass]) => (
          <div key={label}>
            <h3><Icon size={14} className={toneClass}/> {label} ({rows.length})</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Security / Sector</th>
                    <th>1D Change</th>
                    <th title="ETF daily return minus SPY daily return, in percentage points">vs SPY (pp)</th>
                    <th>Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => {
                    const excess = (r.excess_1d * 100).toFixed(2);
                    return (
                      <tr key={r.etf}>
                        <td>
                          <button className="ticker" onClick={() => onSelect(r.etf)}>
                            <b>{r.etf}</b>
                            <small>{r.sector}</small>
                          </button>
                        </td>
                        <td className={r.return_1d > 0 ? 'positive' : 'negative'}>{pct(r.return_1d)}</td>
                        <td className={r.excess_1d >= 0 ? 'positive' : 'negative'}>{r.excess_1d > 0 ? `+${excess}` : excess}</td>
                        <td>
                          {r.excess_1d > 0.01 && <span className="badge-pill positive"><Zap size={10}/> Outperforming</span>}
                          {r.excess_1d < -0.01 && <span className="badge-pill negative">Underperforming</span>}
                          {Math.abs(r.excess_1d) <= 0.01 && <span className="badge-pill muted">In-Line</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!rows.length && <p className="coverage-note">{groups.covered ? 'No securities match current threshold filter.' : 'No aligned daily returns available.'}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}


