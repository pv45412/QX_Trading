// Scratch: browser-verify the Context and Settings pages, then screenshot.
const { chromium } = require("playwright");

let pass = 0, fail = 0;
function check(l, c, e = "") { if (c) { pass++; console.log(`  PASS  ${l} ${e}`); } else { fail++; console.log(`  FAIL  ${l} ${e}`); } }

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1020 } });
  page.setDefaultTimeout(600000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/400|503/.test(m.text())) errors.push("console: " + m.text()); });

  console.log("== context ==");
  await page.goto("http://127.0.0.1:8790/context", { waitUntil: "domcontentloaded" });
  const ready = await page.waitForFunction(() => {
    const lv = document.querySelector("#lv"), gx = document.querySelector("#gx");
    return lv && gx && /Price/.test(lv.textContent) && (/Net gamma/.test(gx.textContent) || /failed|error/i.test(gx.textContent));
  }, { timeout: 300000 }).then(() => true).catch(() => false);
  check("context data loaded", ready);

  const lv = await page.$eval("#lv", (e) => e.textContent);
  check("levels show prior day + ATR", /Prior close/.test(lv) && /ATR/.test(lv));
  check("levels show VWAP bands", /VWAP \+2/.test(lv) && /VWAP -2/.test(lv));
  // The futures panel now resolves 7 roots (index + energy + metals + crypto), so
  // wait for it to finish rather than sampling it mid-load.
  await page.waitForFunction(() => {
    const el = document.querySelector("#fut");
    return el && !/Loading/i.test(el.textContent) && /\/ES/.test(el.textContent);
  }, { timeout: 300000 }).catch(() => {});
  const fut = await page.$eval("#fut", (e) => e.textContent);
  check("futures panel shows /ES and /NQ", /\/ES/.test(fut) && /\/NQ/.test(fut), fut.slice(0, 60));
  check("futures panel includes the new roots", /\/CL/.test(fut) && /\/BTC/.test(fut), fut.slice(0, 90));
  const gx = await page.$eval("#gx", (e) => e.textContent);
  check("gamma panel shows flip + walls", /Gamma flip/.test(gx) && /Call wall/.test(gx) && /Put wall/.test(gx));
  check("gamma declares settlement provenance", /Settlement provenance/.test(gx));
  const profRows = await page.$$eval("#gxprofile tbody tr", (rs) => rs.length);
  check("strike profile table rendered", profRows > 10, `${profRows} strikes`);
  const kpiCount = await page.$$eval("#gx .kpi", (ks) => ks.length);
  check("four gamma KPIs", kpiCount === 4, `${kpiCount}`);

  // Switching symbol must reload.
  await page.selectOption("#csym", "QQQ");
  await page.waitForTimeout(9000);
  const lv2 = await page.$eval("#lv", (e) => e.textContent);
  check("symbol switch reloads levels", /Price/.test(lv2));

  console.log("== settings ==");
  await page.goto("http://127.0.0.1:8790/settings", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => /Client ID/.test(document.querySelector("#creds").textContent), { timeout: 300000 });
  // The health probes and notes are filled by the same async load; wait for them.
  await page.waitForFunction(() => {
    const h = document.querySelector("#hlth"), n = document.querySelector("#notes");
    return h && n && /Trader probe/.test(h.textContent) && n.textContent.trim().length > 20;
  }, { timeout: 300000 }).catch(() => {});
  const creds = await page.$eval("#creds", (e) => e.textContent);
  check("credentials panel lists client id + secret presence", /Client ID/.test(creds) && /Client secret/.test(creds));
  check("redirect URI shown", /Redirect URI/.test(creds));
  check("env path shown", /\.env file/.test(creds));
  const tok = await page.$eval("#tok", (e) => e.textContent);
  check("token state panel", /Access token valid/.test(tok) && /Refresh token valid/.test(tok));
  const hlth = await page.$eval("#hlth", (e) => e.textContent);
  check("health probes shown", /Market data probe/.test(hlth) && /Trader probe/.test(hlth), hlth.slice(0, 60));
  const notes = await page.$eval("#notes", (e) => e.textContent);
  check("secret-handling notes listed", /never exposed/.test(notes) || /server-side/.test(notes));

  const pageHtml = await page.content();
  // Assert the secret never reaches the DOM WITHOUT embedding the secret itself.
  // Read it from the environment/\.env at run time; skip if unavailable so this
  // test file carries no credential.
  let secretValue = process.env.QX_SCHWAB_CLIENT_SECRET || "";
  if (!secretValue) {
    try {
      const fs = require("fs");
      const env = fs.readFileSync("C:/Project/2026/.env", "utf8");
      const line = env.split(/\r?\n/).find((l) => l.startsWith("QX_SCHWAB_CLIENT_SECRET="));
      if (line) secretValue = line.split("=").slice(1).join("=").trim();
    } catch (e) { /* leave empty */ }
  }
  const containsSecret = secretValue.length >= 12 && pageHtml.includes(secretValue);
  check("no client secret value in DOM", !containsSecret,
    secretValue ? "(checked against the configured secret)" : "(no secret available to check)");
  check("no access token in DOM", !/"access_token"\s*:\s*"/.test(pageHtml));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | ") || "clean");

  const fs = require("fs");
  fs.mkdirSync("C:/Project/2026/data/reports/qx_ui", { recursive: true });
  await page.goto("http://127.0.0.1:8790/context", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(12000);
  await page.screenshot({ path: "C:/Project/2026/data/reports/qx_ui/context-desktop.png", fullPage: true });
  await page.goto("http://127.0.0.1:8790/settings", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(6000);
  await page.screenshot({ path: "C:/Project/2026/data/reports/qx_ui/settings-desktop.png", fullPage: true });
  check("screenshots captured", fs.existsSync("C:/Project/2026/data/reports/qx_ui/context-desktop.png")
    && fs.existsSync("C:/Project/2026/data/reports/qx_ui/settings-desktop.png"));

  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto("http://127.0.0.1:8790/context", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(9000);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("context no horizontal overflow at 420px", overflow <= 8, `overflow=${overflow}px`);

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error("SUITE ERROR:", e.message); process.exit(2); });
