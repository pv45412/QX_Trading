import React, { useState, useEffect } from 'react';
import WorkspaceNavigation from './WorkspaceNavigation';
import { workspaceHref } from './workspace-context';

export function QXBentoDashboardLayout({ route, context, children }) {
  const page = route ? route.page : 'relative_strength';

  const [telemetry, setTelemetry] = useState({
    spxPrice: '5,842.10',
    spxChange: '+0.34%',
    vixPrice: '14.25',
    vixChange: '-2.10%',
    netCvd: '+14,820',
    portfolioDelta: '+142.50',
    isLive: true,
    statusText: '● LIVE STREAM ACTIVE'
  });

  useEffect(() => {
    let isMounted = true;
    const fetchHeaderTelemetry = async () => {
      try {
        const res = await fetch('/api/terminal/watchlist');
        if (res.ok && isMounted) {
          const watchlist = await res.json();
          if (Array.isArray(watchlist) && watchlist.length > 0) {
            const spxObj = watchlist.find(w => w.symbol === 'SPX');
            const isBlocked = watchlist.some(w => w.as_of && w.as_of.includes('BLOCKED'));
            setTelemetry(prev => ({
              ...prev,
              spxPrice: spxObj && spxObj.price ? (Number(spxObj.price)).toLocaleString(undefined, { minimumFractionDigits: 2 }) : prev.spxPrice,
              spxChange: spxObj && spxObj.change ? spxObj.change : prev.spxChange,
              isLive: !isBlocked,
              statusText: isBlocked ? '○ MARKET FEED CACHED' : '● LIVE STREAM ACTIVE'
            }));
          }
        }
      } catch (e) {
        if (isMounted) {
          setTelemetry(prev => ({
            ...prev,
            isLive: false,
            statusText: '○ MARKET FEED CACHED'
          }));
        }
      }
    };
    fetchHeaderTelemetry();
  }, []);

  const THEMES = [
    { id: 'warm', name: 'Warm Obsidian', accent: '#d9a05b' },
    { id: 'mocha', name: 'Mocha Dark', accent: '#c2a688' },
    { id: 'neutral', name: 'Neutral Slate', accent: '#8da4be' },
    { id: 'stealth', name: 'Stealth Soft', accent: '#d4a373' },
  ];

  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('qx_theme') || 'warm';
    } catch (e) {
      return 'warm';
    }
  });

  useEffect(() => {
    try {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('qx_theme', theme);
    } catch (e) {
      // fallback
    }
  }, [theme]);

  const navItems = [
    { page: 'command_center', label: 'Terminal', icon: '⚡' },
    { page: 'options_ideas', label: 'Ideas Hub', icon: '💡' },
    { page: 'spx_nq_futures', label: 'Futures', icon: '📈' },
    { page: 'scan', label: 'Scanner', icon: '📊' },
    { page: 'idea_tracking', label: 'Advisor', icon: '🛡️' },
    { page: 'data_cache', label: 'System', icon: '⚙️' },
  ];

  return (
    <div className="qx-app-shell">
      {/* 1. Top Telemetry & Global Status Header Bar (56px) */}
      <header className="qx-top-header">
        <div className="qx-header-brand">
          <span className="qx-brand-title">QX <span className="qx-brand-accent">PLATFORM</span></span>
          <span className={`qx-live-badge ${!telemetry.isLive ? 'qx-cached-badge' : ''}`}>
            {telemetry.statusText}
          </span>
        </div>

        {/* Eye-Comfort Theme Switcher */}
        <div className="qx-theme-selector" aria-label="Theme Switcher">
          <span className="qx-theme-label">Theme</span>
          {THEMES.map(t => (
            <button
              key={t.id}
              className={`qx-theme-btn ${theme === t.id ? 'active' : ''}`}
              onClick={() => setTheme(t.id)}
              title={`${t.name} Eye-Comfort Theme`}
            >
              <span className="qx-theme-dot" style={{ backgroundColor: t.accent }} />
              {t.name}
            </button>
          ))}
        </div>

        <div className="qx-header-telemetry">
          <div className="qx-telemetry-item">SPX: <strong>{telemetry.spxPrice}</strong> <span className={telemetry.spxChange.startsWith('-') ? 'qx-pct-down' : 'qx-pct-up'}>{telemetry.spxChange}</span></div>
          <div className="qx-telemetry-item">VIX: <strong>{telemetry.vixPrice}</strong> <span className="qx-pct-down">{telemetry.vixChange}</span></div>
          <div className="qx-telemetry-item">NET CVD: <strong className="qx-pct-up">{telemetry.netCvd}</strong></div>
          <div className="qx-telemetry-item">PORTFOLIO DELTA: <strong className="qx-pct-up">{telemetry.portfolioDelta}</strong></div>
        </div>
      </header>


      {/* 2. Main Workspace Container */}
      <div className="qx-workspace-body">
        {/* Left Compact Sidebar (64px) */}
        <aside className="qx-left-sidebar" aria-label="Workspace Sidebar">
          {navItems.map((item) => {
            const isActive = page === item.page;
            return (
              <a
                key={item.page}
                href={workspaceHref(item.page, context)}
                className={`qx-sidebar-btn ${isActive ? 'qx-sidebar-active' : ''}`}
                title={item.label}
              >
                <span className="qx-sidebar-icon">{item.icon}</span>
                <span className="qx-sidebar-label">{item.label}</span>
              </a>
            );
          })}
        </aside>

        {/* Dynamic Bento Grid Main Content Stage */}
        <div className="qx-main-stage">
          <WorkspaceNavigation route={route} context={context} />
          <div className="qx-bento-grid-container">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

export default QXBentoDashboardLayout;
