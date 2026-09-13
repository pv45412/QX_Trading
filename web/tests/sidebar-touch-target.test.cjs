const {test} = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '../..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const styles = execFileSync(python, ['-c',
  'from types import SimpleNamespace; from qx.ui.app_shell import inject_app_styles; '
  + 'inject_app_styles(SimpleNamespace(html=print))'], {cwd: root, encoding: 'utf8'});
const selectors = [
  '[data-testid="stExpandSidebarButton"]',
  '[data-testid="stSidebarCollapsedControl"] button',
  '[data-testid="stSidebarCollapseButton"] button'
];

for (const width of [390, 1440]) {
  for (const fontSize of [14, 16, 20]) {
    test(`sidebar targets survive late component CSS at ${width}px / ${fontSize}px font`, async () => {
      const browser = await chromium.launch({channel: 'msedge', headless: true});
      try {
        const page = await browser.newPage({viewport: {width, height: 844}});
        await page.setContent(`${styles}
          <header data-testid="stHeader"><div data-testid="stToolbar">
            <button data-testid="stExpandSidebarButton">Open</button>
          </div></header>
          <div data-testid="stSidebarCollapsedControl"><button>Legacy open</button></div>
          <section data-testid="stSidebar" aria-expanded="true">
            <div data-testid="stSidebarCollapseButton"><button>Close</button></div>
          </section>`);
        // Higher-specificity rules loaded later must not shrink essential controls.
        await page.addStyleTag({content: `
          html {font-size: ${fontSize}px;}
          header button[data-testid="stExpandSidebarButton"],
          div[data-testid="stSidebarCollapsedControl"] button,
          section [data-testid="stSidebarCollapseButton"] button {
            width: 28px; height: 28px; min-width: 28px; min-height: 28px;
          }
        `});
        for (const selector of selectors) {
          const button = page.locator(selector);
          const rect = await button.boundingBox();
          const minimum = Math.max(44, 2.75 * fontSize);
          assert.ok(rect.width >= minimum && rect.height >= minimum,
            `${selector}: ${JSON.stringify(rect)}`);
          await button.click({trial: true});
        }
      } finally {
        await browser.close();
      }
    });
  }
}
