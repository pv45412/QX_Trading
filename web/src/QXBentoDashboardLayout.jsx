import React, {useEffect, useState} from 'react';
import WorkspaceNavigation from './WorkspaceNavigation';

const themes = [
  {id: 'warm', name: 'Warm Obsidian', accent: '#d9a05b'},
  {id: 'mocha', name: 'Mocha Dark', accent: '#c2a688'},
  {id: 'neutral', name: 'Neutral Slate', accent: '#8da4be'},
  {id: 'stealth', name: 'Stealth Soft', accent: '#d4a373'},
];

export function QXBentoDashboardLayout({route, context, children}) {
  const destination = route?.targetPage || route?.page || 'research';
  const isSystemWorkspace = destination === 'system';
  let workspaceMode = 'READ-ONLY PRODUCT WORKSPACE';
  if (isSystemWorkspace) workspaceMode = 'LOCAL CONTROL MODE';
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('qx_theme') || 'warm';
    } catch (_error) {
      return 'warm';
    }
  });

  useEffect(() => {
    try {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('qx_theme', theme);
    } catch (_error) {
      // The shell remains usable when browser storage is unavailable.
    }
  }, [theme]);

  return <div className="qx-app-shell">
    <header className="qx-top-header">
      <div className="qx-header-brand">
        <span className="qx-brand-title">QX <span className="qx-brand-accent">PLATFORM</span></span>
        <span className="qx-live-badge qx-cached-badge">{workspaceMode}</span>
      </div>
      <div className="qx-shell-location" aria-label="Current product destination">
        <span>{route?.title || 'QX Workspace'}</span>
        <strong>{context?.horizon || 'DAY'}</strong>
      </div>
      <div className="qx-theme-selector" aria-label="Theme Switcher">
        <span className="qx-theme-label">Theme</span>
        {themes.map(option => <button
          key={option.id}
          className={`qx-theme-btn ${theme === option.id ? 'active' : ''}`}
          onClick={() => setTheme(option.id)}
          title={`${option.name} Eye-Comfort Theme`}
        >
          <span className="qx-theme-dot" style={{backgroundColor: option.accent}}/>
          {option.name}
        </button>)}
      </div>
    </header>

    <div className={`qx-workspace-body qx-destination-${destination}`}>
      <div className="qx-main-stage">
        <WorkspaceNavigation route={route} context={context}/>
        <div className="qx-bento-grid-container">{children}</div>
      </div>
    </div>
  </div>;
}

export default QXBentoDashboardLayout;
