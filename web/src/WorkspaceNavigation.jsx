import React from 'react';
import { workspaceContextItems, workspaceHref } from './workspace-context';
import { workspaceHomes, workspaceRoutes } from './workspace-routes';
import { Zap, Target, Activity, Award, BarChart2, TrendingUp, Sparkles, PieChart } from 'lucide-react';

export default function WorkspaceNavigation({ route, context }) {
  const jumpLinks = [
    { label: 'Options Ideas Hub', hash: '#options-ideas-hub', key: 'F0', icon: Award, color: '#10b981' },
    { label: 'Research Studio', hash: '#research-studio', key: 'F1', icon: Target, color: '#38bdf8' },
    { label: 'Options Scanner V1', hash: '#options-scanner-v1', key: 'F2', icon: Zap, color: '#38bdf8' },
    { label: 'SPX Command', hash: '#spx-dashboard', key: 'F2', icon: Zap, color: '#00f2fe' },
    { label: 'Prompt Studio', hash: '#daily-prompt', key: 'F3', icon: Target, color: '#00e676' },
    { label: 'Day Trader Terminal', hash: '#qx-terminal', key: 'F4', icon: Activity, color: '#ffab00' },
    { label: 'QX Suite', hash: '#qx-suite', key: 'F5', icon: Award, color: '#3b82f6' },
    { label: 'Sector Ranking', hash: '#ranking', key: 'F6', icon: BarChart2, color: '#a78bfa' },
    { label: 'Market Movers', hash: '#movers', key: 'F7', icon: TrendingUp, color: '#f43f5e' },
    { label: 'AI Review', hash: '#ai-review', key: 'F8', icon: Sparkles, color: '#38bdf8' },
    { label: 'Holdings', hash: '#holdings', key: 'F9', icon: PieChart, color: '#4ade80' },
  ];

  const handleJump = (hash) => {
    document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <>
      <nav className="workspace-nav" aria-label="Workspace pages">
        {workspaceHomes.map(home => (
          <a
            key={home.page}
            href={workspaceHref(home.page, context)}
            aria-current={home.workspace === route?.workspace ? 'page' : undefined}
          >
            {home.workspace}
          </a>
        ))}
      </nav>

      {/* Institutional Command Bar & Hotkeys Strip */}
      <div style={{
        background: 'rgba(15, 23, 42, 0.75)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '8px',
        padding: '8px 12px',
        margin: '10px 0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', fontWeight: 700, color: '#00f2fe' }}>
          <span style={{ background: 'rgba(0, 242, 254, 0.15)', color: '#00f2fe', padding: '2px 6px', borderRadius: '4px' }}>
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
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                color: '#cbd5e1',
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
              <span style={{ fontSize: '9px', background: 'rgba(255,255,255,0.08)', padding: '1px 4px', borderRadius: '3px', color: '#94a3b8' }}>
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
