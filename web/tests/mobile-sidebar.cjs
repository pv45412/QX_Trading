const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const {chromium} = require('playwright');

// Read-only interaction regression against an already-running Streamlit server.
// Run: node tests/mobile-sidebar.cjs
// Optional: --local-css tests the working-tree shell without restarting a stale server.
// SCANNER_SIDEBAR_ROUTES=backtest,strategy_lab and SCANNER_SIDEBAR_WIDTHS=390 narrow a run.
const root = path.resolve(__dirname, '../..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
function readPython(code) {
  return execFileSync(python, ['-c', code], {cwd: root, encoding: 'utf8'});
}

// Every registered page plus legacy subview routes (Pipeline, Workflows, Snapshots).
// Importing the registry does not render pages or run their data actions.
function routeInventory() {
  return JSON.parse(readPython(
    'import json; from qx.ui.pages import PAGES; from qx.ui import streamlit_app as app; '
    + 'routes = [next(k for k, v in app.PAGE_ROUTE_TABS.items() if v == p.title) for p in PAGES]; '
    + 'routes += list(getattr(app, "LEGACY_VIEWS", {})); '
    + 'print(json.dumps({"routes": list(dict.fromkeys(routes)), "titles": app.PAGE_ROUTE_TABS}))'
  ));
}

const essentialSidebar = {
  heatmap: ['Heatmap min score'],
  data_cache: ['Cache period', 'Coverage universe'],
  jobs: ['Pipeline universe', 'Pipeline history', 'Pipeline data source', 'Pipeline profile',
    'Pattern bars', 'Max range %', 'Force data refresh'],
  workflow_history: ['Workflow runs'],
  command_snapshots: ['Command snapshots']
};
essentialSidebar.pipeline = essentialSidebar.jobs;
essentialSidebar.pipeline_control = essentialSidebar.jobs;
const bodyActions = {
  backtest: 'Run backtest', strategy_lab: 'Run strategy comparison',
  jobs: 'Run full pipeline', pipeline: 'Run full pipeline', pipeline_control: 'Run full pipeline'
};
const widgetSelector = 'input:not([type="hidden"]), textarea, select, [role="slider"], button';

function namedControl(page, role, name) {
  return page.getByRole(role, {name: new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$')});
}

const reopenSelector = '[data-testid="stExpandSidebarButton"], '
  + '[data-testid="stSidebarCollapsedControl"] button';
const closeSelector = '[data-testid="stSidebarCollapseButton"] button';
const chromeSelector = '.stDeployButton, .stAppDeployButton, #MainMenu, '
  + '[data-testid="stToolbarActions"], [data-testid="stHeaderActionElements"], '
  + '[data-testid="stSidebarNav"], [data-testid="stDecoration"], [data-testid="stStatusWidget"]';

async function settle(page) {
  await page.waitForFunction(() => {
    const app = document.querySelector('[data-testid="stApp"]');
    return app && app.dataset.testScriptState !== 'running';
  }, {}, {timeout: 60000});
  // Streamlit sidebar transitions last 300ms. Check after animation and injected styles settle.
  await page.waitForTimeout(700);
}

async function assertOnscreen(locator, label) {
  assert.equal(await locator.count(), 1, `${label}: expected one control`);
  const state = await locator.evaluate(element => {
    // BaseWeb paints the label instead of its transparent native checkbox/radio input.
    const visual = element.matches('input[type="checkbox"], input[type="radio"]')
      ? element.closest('label') : element.closest('[data-baseweb="select"]') || element;
    const rect = visual.getBoundingClientRect();
    const style = getComputedStyle(visual);
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return {
      visible: style.visibility === 'visible' && style.display !== 'none',
      unobscured: !!hit && visual.contains(hit),
      onscreen: rect.width > 0 && rect.height > 0 && rect.left >= 0 && rect.top >= 0
        && rect.right <= innerWidth + 1 && rect.bottom <= innerHeight + 1,
      rect: rect.toJSON()
    };
  });
  assert.equal(state.visible && state.onscreen && state.unobscured,
    true, `${label}: ${JSON.stringify(state)}`);
}

async function scrollControl(locator) {
  await locator.evaluate(element => {
    const visual = element.matches('input[type="checkbox"], input[type="radio"]')
      ? element.closest('label') : element.closest('[data-baseweb="select"]') || element;
    visual.scrollIntoView({block: 'center', inline: 'nearest'});
  });
}

async function tabTo(page, locator, label) {
  for (let step = 0; step < 180; step++) {
    await page.keyboard.press('Tab');
    if (await locator.evaluate(element => element === document.activeElement)) {
      await assertOnscreen(locator, label);
      return;
    }
  }
  assert.fail(`${label}: unreachable using Tab`);
}

async function discoverControls(scope, beforeButton = null) {
  const targets = [];
  const disabled = [];
  const collapsed = [];
  const before = beforeButton && await beforeButton.elementHandle();
  for (const control of await scope.locator(widgetSelector).all()) {
    const metadata = await control.evaluate((element, before) => ({
      name: element.getAttribute('aria-label') || element.closest('[data-testid="stElementContainer"]')
        ?.querySelector('[data-testid="stWidgetLabel"]')?.textContent || element.textContent,
      disabled: element.disabled || element.getAttribute('aria-disabled') === 'true',
      inactiveRadio: element.matches('input[type="radio"]') && !element.checked,
      numberStepper: element.tagName === 'BUTTON' && !!element.closest('[data-testid="stNumberInput"]'),
      afterForm: before && !(element.compareDocumentPosition(before) & Node.DOCUMENT_POSITION_FOLLOWING),
      closedDetails: before && !!element.closest('details:not([open])')
    }), before);
    if (metadata.inactiveRadio || metadata.numberStepper || metadata.afterForm) continue;
    if (metadata.disabled) {disabled.push(metadata.name); continue;}
    if (metadata.closedDetails) {collapsed.push(metadata.name); continue;}
    targets.push([`${targets.length}: ${metadata.name}`, control]);
  }
  return {targets, disabled, collapsed};
}

async function checkControls(page, targets, region) {
  for (const [name, control] of targets) {
    assert.equal(await control.count(), 1, `${name}: missing/ambiguous control`);
    assert.equal(await control.isEnabled(), true, `${name}: disabled`);
    await scrollControl(control);
    await assertOnscreen(control, name);
    await control.evaluate((element, id) => {element.dataset.sidebarAuditTarget = id;}, `${region}:${name}`);
  }
  // Walk the real tab order. No .focus(), widget value changes, or action activation.
  const pending = new Map(targets.map(([name, control]) => [`${region}:${name}`, control]));
  for (let step = 0; pending.size && step < 180; step++) {
    await page.keyboard.press('Tab');
    const name = await page.evaluate(() => document.activeElement?.dataset.sidebarAuditTarget);
    if (pending.has(name)) {
      await assertOnscreen(pending.get(name), `${name} keyboard focus`);
      pending.delete(name);
    }
  }
  assert.deepEqual([...pending.keys()], [], `${region} controls missing from keyboard tab order`);
}

async function assertToggleState(page, expanded) {
  await settle(page);
  assert.equal(await page.getByTestId('stSidebar').getAttribute('aria-expanded'), String(expanded));
  const toggle = page.locator(expanded ? closeSelector : reopenSelector);
  await toggle.scrollIntoViewIfNeeded();
  // The desktop close button must not depend on mouse hover over the sidebar.
  await page.mouse.move(page.viewportSize().width - 1, page.viewportSize().height - 1);
  await assertOnscreen(toggle, expanded ? 'Close sidebar' : 'Open sidebar');
  const rect = await toggle.boundingBox();
  if (rect.width < 44 || rect.height < 44) {
    const diagnostics = await toggle.evaluate(element => ({
      html: element.outerHTML,
      minWidth: getComputedStyle(element).minWidth,
      minHeight: getComputedStyle(element).minHeight,
      transform: getComputedStyle(element).transform,
      rootFont: getComputedStyle(document.documentElement).fontSize,
      appState: document.querySelector('[data-testid="stApp"]')?.dataset.testScriptState,
      sharedStyles: [...document.querySelectorAll('style')]
        .filter(style => style.textContent.includes('--qx-sidebar-bg:')).length
    }));
    console.log(JSON.stringify({sidebarTouchTargetFailure: diagnostics}));
  }
  assert.ok(rect.width >= 44 && rect.height >= 44,
    `Sidebar ${expanded ? 'close' : 'reopen'} needs a 44px touch target: ${JSON.stringify(rect)}`);
  await toggle.click({trial: true});
}

async function checkRoute(page, route, titles, localCss) {
  const url = new URL(process.env.SCANNER_STREAMLIT_URL || 'http://localhost:8501/');
  url.searchParams.set('page', route);
  await page.goto(url.href);
  await page.locator('.qx-page-header').waitFor({timeout: 30000});
  await settle(page);
  if (localCss) {
    const replaced = await page.evaluate(css => {
      const styles = [...document.querySelectorAll('style')]
        .filter(style => style.textContent.includes('--qx-sidebar-bg:'));
      for (const style of styles) style.textContent = css;
      return styles.length;
    }, localCss);
    assert.ok(replaced > 0, 'No shared app stylesheet found for local-CSS verification');
    await settle(page);
  }
  assert.equal(titles[new URL(page.url()).searchParams.get('page')], titles[route]);
  assert.deepEqual(await page.getByTestId('stException').allTextContents(), []);
  const sidebar = page.getByTestId('stSidebar');
  if (await sidebar.getAttribute('aria-expanded') === 'true') {
    await assertToggleState(page, true);
    await page.locator(closeSelector).click();
  }
  await assertToggleState(page, false);
  await page.locator(reopenSelector).click();
  await assertToggleState(page, true);

  // Discover DOM controls even when CSS hides them. Do not filter by :visible.
  const {targets, disabled} = await discoverControls(sidebar.getByTestId('stSidebarUserContent'));
  for (const name of essentialSidebar[route] || []) {
    assert.ok(targets.some(([label]) => label.endsWith(name)), `${name}: missing essential sidebar control`);
  }
  await checkControls(page, targets, 'sidebar');

  await tabTo(page, page.locator(closeSelector), 'Close sidebar keyboard focus');
  assert.equal(await page.locator(closeSelector).evaluate(element => {
    const style = getComputedStyle(element);
    return style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2;
  }), true, 'Close keyboard focus needs a visible outline');
  await page.keyboard.press('Enter');
  await assertToggleState(page, false);
  await tabTo(page, page.locator(reopenSelector), 'Open sidebar keyboard focus');
  assert.equal(await page.locator(reopenSelector).evaluate(element => {
    const style = getComputedStyle(element);
    return style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2;
  }), true, 'Reopen keyboard focus needs a visible outline');
  await page.keyboard.press('Enter');
  await assertToggleState(page, true);
  await page.locator(closeSelector).click();
  await assertToggleState(page, false);

  let formControls = 0;
  let collapsedFormControls = [];
  if (route === 'backtest' || route === 'strategy_lab') {
    const action = namedControl(page, 'button', bodyActions[route]);
    const form = await discoverControls(page.getByTestId('stMain'), action);
    assert.ok(form.targets.length > 0, `${route}: no main-page evaluation inputs found`);
    await checkControls(page, form.targets, 'evaluation');
    formControls = form.targets.length;
    collapsedFormControls = form.collapsed;
  }
  if (bodyActions[route]) {
    const name = bodyActions[route];
    const button = namedControl(page, 'button', name);
    if (await button.evaluate(element => !!element.closest('[data-testid="stSidebar"]'))) {
      assert.ok(targets.some(([label]) => label.endsWith(name)), `${name}: not checked in sidebar`);
    } else {
      await scrollControl(button);
      await assertOnscreen(button, name);
      await tabTo(page, button, `${name} keyboard focus (not activated)`);
    }
  }
  for (const chrome of await page.locator(chromeSelector).all()) {
    assert.equal(await chrome.isVisible(), false, 'Nonessential chrome is visible');
  }
  assert.deepEqual(await page.getByTestId('stException').allTextContents(), []);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(await page.evaluate(() => window.sidebarAuditBlockedActions), []);
  return {sidebarControls: targets.length, disabledControls: disabled, formControls, collapsedFormControls};
}

async function main() {
  let localCss;
  if (process.argv.includes('--local-css')) {
    const html = readPython(
      'from types import SimpleNamespace; from qx.ui.app_shell import inject_app_styles; '
      + 'inject_app_styles(SimpleNamespace(html=print))'
    );
    localCss = html.match(/<style>([\s\S]*?)<\/style>/)[1];
  }
  const {routes, titles} = routeInventory();
  const selected = process.env.SCANNER_SIDEBAR_ROUTES?.split(',');
  if (selected) assert.ok(selected.every(route => routes.includes(route)), 'Unknown route filter');
  const widths = (process.env.SCANNER_SIDEBAR_WIDTHS || '390,1440').split(',').map(Number);
  assert.ok(widths.every(width => Number.isInteger(width) && width >= 320), 'Invalid viewport width');
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const results = [];
  try {
    for (const width of widths) {
      for (const route of routes) {
        if (selected && !selected.includes(route)) continue;
        const context = await browser.newContext({viewport: {width, height: 844}});
        await context.addInitScript(() => {
          window.sidebarAuditBlockedActions = [];
          // Fail closed if a future test edit accidentally activates an application action.
          document.addEventListener('click', event => {
            const button = event.target.closest('button, a, input[type="submit"]');
            if (!button || button.matches('[data-testid="stExpandSidebarButton"]')
              || button.closest('[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapseButton"]')) return;
            window.sidebarAuditBlockedActions.push(button.textContent);
            event.preventDefault();
            event.stopImmediatePropagation();
          }, true);
        });
        const page = await context.newPage();
        page.setDefaultTimeout(10000);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const result = {route, width, mode: localCss ? 'local-css' : 'server-css'};
        try {
          Object.assign(result, await checkRoute(page, route, titles, localCss));
          assert.deepEqual(errors, []);
          result.passed = true;
        } catch (error) {
          result.passed = false;
          result.error = error.message;
        } finally {
          results.push(result);
          console.log(JSON.stringify(result));
          await context.close();
        }
      }
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify({passed: results.filter(row => row.passed).length,
    failed: results.filter(row => !row.passed).length}));
  if (results.some(row => !row.passed)) process.exitCode = 1;
}

if (require.main === module) main().catch(error => {console.error(error); process.exitCode = 1;});
module.exports = {routeInventory};
