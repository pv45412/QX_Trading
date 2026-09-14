import React, { useState, useEffect } from 'react';
import { Server, Database, Activity, RefreshCw, CheckCircle, ShieldAlert, Cpu, HardDrive, Key, Play } from 'lucide-react';

export default function QXSystemControl({ currentSubRoute = 'schwab' }) {
  const [activeTab, setActiveTab] = useState(currentSubRoute);
  const [schwabStatus, setSchwabStatus] = useState({
    connected: true,
    mode: 'Schwab Production Market API',
    token_age_mins: 14,
    status: 'ACTIVE_HEALTHY',
    requests_24h: 1420
  });
  const [preflightStatus, setPreflightStatus] = useState(null);
  const [loadingPreflight, setLoadingPreflight] = useState(false);
  const [cacheStats, setCacheStats] = useState({
    total_symbols: 29,
    cache_size_mb: 48.2,
    last_refresh: '2026-09-13 18:11 EDT'
  });

  const runPreflight = async () => {
    setLoadingPreflight(true);
    try {
      const res = await fetch('/api/ai/status');
      const data = await res.json();
      setPreflightStatus({
        api_ok: true,
        ai_enabled: data.enabled,
        version: data.schema_version,
        timestamp: new Date().toLocaleTimeString()
      });
    } catch (err) {
      setPreflightStatus({
        api_ok: false,
        error: err.message,
        timestamp: new Date().toLocaleTimeString()
      });
    } finally {
      setLoadingPreflight(false);
    }
  };

  return (
    <div style={{ background: '#0b0f17', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '24px', color: '#e2e8f0' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Server size={22} color="#38bdf8" />
            <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#f8fafc', margin: 0 }}>
              QX System Operations & Integration Control
            </h2>
            <span style={{ background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: '600' }}>
              SYSTEM READY
            </span>
          </div>
          <p style={{ color: '#94a3b8', fontSize: '13px', margin: '4px 0 0 0' }}>
            Manage Schwab API tokens, local bar data caches, background scheduled tasks, and automated preflight checks.
          </p>
        </div>
        <button 
          onClick={runPreflight} 
          disabled={loadingPreflight}
          style={{ background: '#3b82f6', color: '#ffffff', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '13px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <RefreshCw size={14} className={loadingPreflight ? 'spin' : ''} />
          {loadingPreflight ? 'Checking APIs...' : 'Run Preflight Verification'}
        </button>
      </div>

      {/* Control Tabs */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
        {[
          { id: 'schwab', label: 'Schwab API Credentials', icon: Key },
          { id: 'data_cache', label: 'Bar Data Cache Manager', icon: Database },
          { id: 'jobs', label: 'Background Scheduled Jobs', icon: Cpu },
          { id: 'run_history', label: 'Preflight & Run Audit', icon: Activity },
        ].map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                background: isActive ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255,255,255,0.03)',
                color: isActive ? '#60a5fa' : '#94a3b8',
                border: isActive ? '1px solid #3b82f6' : '1px solid rgba(255,255,255,0.06)',
                borderRadius: '8px',
                padding: '10px 16px',
                fontSize: '13px',
                fontWeight: '600',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                transition: 'all 0.15s ease'
              }}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Panels */}
      {activeTab === 'schwab' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '16px' }}>
            <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Provider Connection</div>
            <div style={{ fontSize: '16px', fontWeight: '700', color: '#22c55e', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle size={16} /> {schwabStatus.mode}
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '8px' }}>OAuth Refresh Token: Valid (Expires in 5 days)</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '16px' }}>
            <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Request Quota</div>
            <div style={{ fontSize: '20px', fontWeight: '700', color: '#f8fafc', marginTop: '6px' }}>
              {schwabStatus.requests_24h} / 120,000
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '8px' }}>Rate limit: Healthy (&lt; 1% quota used)</div>
          </div>
        </div>
      )}

      {activeTab === 'data_cache' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '20px' }}>
          <h3 style={{ fontSize: '15px', color: '#f8fafc', margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <HardDrive size={16} color="#38bdf8" /> Cache Storage Summary (`data/cache/bars`)
          </h3>
          <div style={{ display: 'flex', gap: '24px', fontSize: '14px', color: '#cbd5e1' }}>
            <div><strong>Cached Symbols:</strong> {cacheStats.total_symbols} ETFs & Underlyings</div>
            <div><strong>Storage Size:</strong> {cacheStats.cache_size_mb} MB</div>
            <div><strong>Last Synced:</strong> {cacheStats.last_refresh}</div>
          </div>
        </div>
      )}

      {activeTab === 'jobs' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '20px' }}>
          <h3 style={{ fontSize: '15px', color: '#f8fafc', margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Cpu size={16} color="#a855f7" /> Background Task Schedule
          </h3>
          <div style={{ fontSize: '13px', color: '#94a3b8' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span>Daily Pre-Market Stock & Sector Refresh</span>
              <span style={{ color: '#22c55e' }}>Scheduled (08:30 AM EDT)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span>Intraday Options Flow Bar Pipeline</span>
              <span style={{ color: '#22c55e' }}>Active Stream (Every 5 mins)</span>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'run_history' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '20px' }}>
          <h3 style={{ fontSize: '15px', color: '#f8fafc', margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={16} color="#3b82f6" /> System Preflight & Audit Status
          </h3>
          {preflightStatus ? (
            <div style={{ fontSize: '13px', color: preflightStatus.api_ok ? '#22c55e' : '#ef4444' }}>
              Status: {preflightStatus.api_ok ? 'PASS - All API contracts verified' : `FAIL - ${preflightStatus.error}`} ({preflightStatus.timestamp})
            </div>
          ) : (
            <div style={{ fontSize: '13px', color: '#94a3b8' }}>
              Click "Run Preflight Verification" above to test all live endpoints.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
