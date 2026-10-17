import React from 'react';
import {workspaceContextItems, workspaceHref} from './workspace-context';
import {legacyWorkspaceRoutes, workspaceHomes} from './workspace-routes';

export default function WorkspaceNavigation({route, context}) {
  const handleNavigate = (event, targetPage) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    const href = workspaceHref(targetPage, context);
    const origin = typeof location !== 'undefined' ? location.origin : 'http://127.0.0.1:5174';
    const url = new URL(href, origin);
    window.history.pushState(null, '', url.pathname + url.search + url.hash);
    window.dispatchEvent(new Event('workspacecontextchange'));
  };

  return <>
    <nav className="workspace-nav" aria-label="Primary product navigation">
      {workspaceHomes.map(home => <a
        key={home.page}
        href={workspaceHref(home.page, context)}
        onClick={event => handleNavigate(event, home.page)}
        aria-current={home.page === (route?.targetPage || route?.page) ? 'page' : undefined}
      >
        {home.workspace}
      </a>)}
    </nav>

    {route?.legacy && <div className="qx-legacy-route-notice" role="status">
      <strong>LEGACY COMPATIBILITY VIEW</strong>
      <span>This route remains available during migration and does not replace canonical Trade state.</span>
    </div>}

    {route?.legacy && <nav className="markets-view-nav" aria-label={`${route.workspace} legacy views`}>
      {legacyWorkspaceRoutes.filter(item => item.workspace === route.workspace).map(item => <a
        key={item.page}
        href={workspaceHref(item.page, context)}
        onClick={event => handleNavigate(event, item.page)}
        aria-current={item.page === route.page ? 'page' : undefined}
      >
        {item.label}
      </a>)}
    </nav>}

    {workspaceContextItems(context).length > 0 && <p
      className="coverage-note qx-workspace-context"
      aria-label="Workspace context"
    >
      {workspaceContextItems(context).map(([label, value]) => `${label}: ${value}`).join(' | ')}
    </p>}
  </>;
}
