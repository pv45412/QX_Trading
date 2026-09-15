import React from 'react';
import WorkspaceNavigation from './WorkspaceNavigation';
import { workspaceHref } from './workspace-context';

export function QXBentoDashboardLayout({ route, context, children }) {
  const page = route ? route.page : 'relative_strength';

  const navItems = [
    { page: 'terminal', label: 'Terminal', icon: '⚡' },
    { page: 'options_ideas', label: 'Ideas Hub', icon: '💡' },
    { page: 'spx_nq_futures', label: 'Futures', icon: '📈' },
    { page: 'scan', label: 'Scanner', icon: '📊' },
    { page: 'position_advisor', label: 'Advisor', icon: '🛡️' },
    { page: 'data_cache', label: 'System', icon: '⚙️' },
  ];

  return (
    <div className="qx-app-shell">
      {/* 1. Top Telemetry & Global Status Header Bar (56px) */}
      <header className="qx-top-header">
        <div className="qx-header-brand">
          <span className="qx-brand-title">QX <span className="qx-brand-accent">PLATFORM</span></span>
          <span className="qx-live-badge">● LIVE STREAM ACTIVE</span>
        </div>
        <div className="qx-header-telemetry">
          <div className="qx-telemetry-item">SPX: <strong>5,842.10</strong> <span className="qx-pct-up">+0.34%</span></div>
          <div className="qx-telemetry-item">VIX: <strong>14.25</strong> <span className="qx-pct-down">-2.10%</span></div>
          <div className="qx-telemetry-item">NET CVD: <strong className="qx-pct-up">+14,820</strong></div>
          <div className="qx-telemetry-item">PORTFOLIO DELTA: <strong className="qx-pct-up">+142.50</strong></div>
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
