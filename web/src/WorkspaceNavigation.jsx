import React from 'react';
import { workspaceContextItems, workspaceHref } from './workspace-context';
import { workspaceHomes, workspaceRoutes } from './workspace-routes';
import { Zap, Target, Activity, Award, BarChart2, TrendingUp, Sparkles, PieChart } from 'lucide-react';

export default function WorkspaceNavigation({ route, context }) {
  const jumpLinks = [
    { label: 'Options Ideas Hub', hash: '#options-ideas-hub', key: 'F0', icon: Award, color: 'var(--qx-positive)' },
    { label: 'Research Studio', hash: '#research-studio', key: 'F1', icon: Target, color: 'var(--qx-accent)' },
    { label: 'Options Scanner V1', hash: '#options-scanner-v1', key: 'F2', icon: Zap, color: 'var(--qx-accent)' },
    { label: 'SPX Command', hash: '#spx-dashboard', key: 'F2', icon: Zap, color: 'var(--qx-accent)' },
    { label: 'Prompt Studio', hash: '#daily-prompt', key: 'F3', icon: Target, color: 'var(--qx-positive)' },
    { label: 'Day Trader Terminal', hash: '#qx-terminal', key: 'F4', icon: Activity, color: 'var(--qx-warning)' },
    { label: 'QX Suite', hash: '#qx-suite', key: 'F5', icon: Award, color: 'var(--qx-accent)' },
    { label: 'Sector Ranking', hash: '#ranking', key: 'F6', icon: BarChart2, color: 'var(--qx-text-secondary)' },
    { label: 'Market Movers', hash: '#movers', key: 'F7', icon: TrendingUp, color: 'var(--qx-negative)' },
    { label: 'AI Review', hash: '#ai-review', key: 'F8', icon: Sparkles, color: 'var(--qx-accent)' },
    { label: 'Holdings', hash: '#holdings', key: 'F9', icon: PieChart, color: 'var(--qx-positive)' },
  ];

  const handleJump = (hash) => {
    const el = document.querySelector(hash);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      const href = workspaceHref('relative_strength', context);
      const origin = typeof location !== 'undefined' ? location.origin : 'http://127.0.0.1:5174';
      const url = new URL(href, origin);
      url.hash = hash;
      window.history.pushState(null, '', url.pathname + url.search + url.hash);
      window.dispatchEvent(new Event('workspacecontextchange'));
    }
  };

  const handleNavigate = (e, targetPage) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    const href = workspaceHref(targetPage, context);
    const origin = typeof location !== 'undefined' ? location.origin : 'http://127.0.0.1:5174';
    const url = new URL(href, origin);
    window.history.pushState(null, '', url.pathname + url.search + url.hash);
    window.dispatchEvent(new Event('workspacecontextchange'));
  };

  return (
    <>
      <nav className="workspace-nav" aria-label="Workspace pages">
        {workspaceHomes.map(home => (
          <a
            key={home.page}
            href={workspaceHref(home.page, context)}
            onClick={e => handleNavigate(e, home.page)}
            aria-current={home.workspace === route?.workspace ? 'page' : undefined}
          >
            {home.workspace}
          </a>
        ))}
      </nav>

      {/* Institutional Command Bar & Hotkeys Strip */}
      <div style={{
        background: 'var(--qx-bg-surface)',
        border: '1px solid var(--qx-border)',
        borderRadius: '8px',
        padding: '8px 12px',
        margin: '10px 0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', fontWeight: 700, color: 'var(--qx-accent)' }}>
          <span style={{ background: 'rgba(217, 160, 91, 0.15)', color: 'var(--qx-accent)', padding: '2px 6px', borderRadius: '4px' }}>
            COMMAND BAR
          </span>
          INSTITUTIONAL QUICK JUMP:
        </div>

        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {jumpLinks.map(item => (
            <button
              key={item.label}
              onClick={() => handleJump(item.hash)}
              style={{
                background: 'var(--qx-bg-canvas)',
                border: '1px solid var(--qx-border-subtle)',
                color: 'var(--qx-text-primary)',
                padding: '4px 8px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                transition: 'all 0.2s ease',
              }}
            >
              <item.icon size={12} color={item.color} />
              <span>{item.label}</span>
              <span style={{ fontSize: '9px', background: 'var(--qx-bg-surface)', padding: '1px 4px', borderRadius: '3px', color: 'var(--qx-text-muted)' }}>
                {item.key}
              </span>
            </button>
          ))}
        </div>
      </div>

      {route && (
        <nav className="markets-view-nav" aria-label={`${route.workspace} views`}>
          {workspaceRoutes.filter(item => item.workspace === route.workspace).map(item => (
            <a
              key={item.page}
              href={workspaceHref(item.page, context)}
              onClick={e => handleNavigate(e, item.page)}
              aria-current={item.page === route.page ? 'page' : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
      )}

      {workspaceContextItems(context).length > 0 && (
        <p
          className="coverage-note"
          aria-label="Workspace context"
          style={{ overflowWrap: 'anywhere' }}
        >
          {workspaceContextItems(context).map(([label, value]) => `${label}: ${value}`).join(' | ')}
        </p>
      )}
    </>
  );
}
