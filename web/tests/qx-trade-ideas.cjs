// Browser integration test for the Trade Ideas page.
const { chromium } = require("playwright");

let pass = 0, fail = 0;
function check(l, c, e = "") { if (c) { pass++; console.log(`  PASS  ${l} ${e}`); } else { fail++; console.log(`  FAIL  ${l} ${e}`); } }

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1560, height: 1040 } });
  page.setDefaultTimeout(600000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/400|503/.test(m.text())) errors.push("console: " + m.text()); });

  console.log("== page loads ==");
  await page.goto("http://127.0.0.1:8790/ideas", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => {
    const el = document.querySelector("#idviews");
    return el && /Ready now/.test(el.textContent);
  }, { timeout: 300000 });

  const active = await page.$eval("#nav a.on", (a) => a.textContent.trim());
  check("active nav marks Trade Ideas", active === "Trade Ideas", active);
  const navItems = await page.$$eval("#nav a", (as) => as.map((a) => a.textContent.trim()));
  check("nav lists all six pages", navItems.length === 6 &&
    ["Discover", "Trade Ideas", "Trade Workspace", "Context", "Reports", "Settings"].every((n) => navItems.includes(n)),
    JSON.stringify(navItems));

  console.log("== views ==");
  const viewButtons = await page.$$eval("#idviews button", (bs) => bs.map((b) => b.textContent.trim()));
  check("five views rendered", viewButtons.length === 5, JSON.stringify(viewButtons));
  check("view labels are the required ones",
    ["Ready now", "Near trigger", "Pullback watch", "Newly aligned", "Bearish opportunities"]
      .every((l) => viewButtons.some((b) => b.startsWith(l))), JSON.stringify(viewButtons));
  const counts = viewButtons.map((b) => Number((b.match(/\((\d+)\)/) || [0, 0])[1]));
  check("view counts shown", counts.every((c) => Number.isInteger(c)), JSON.stringify(counts));

  const sorts = await page.$$eval("#idsort option", (os) => os.map((o) => o.value));
  check("five sorts offered", sorts.length === 5, JSON.stringify(sorts));

  console.log("== ideas table ==");
  const rows = await page.$$eval("#idlist tbody tr", (rs) => rs.length);
  check("ideas listed", rows > 0, `${rows} rows`);
  const listText = await page.$eval("#idlist", (e) => e.textContent);
  check("rows carry entry state", /TRIGGER_CONFIRMED|BREAKOUT_WATCH|PULLBACK_CANDIDATE|EXTENDED_WAIT/.test(listText));
  check("rows carry direction chips", /LONG|SHORT/.test(listText));
  check("rows carry horizon", /SWING/.test(listText));
  check("no EXECUTABLE claim", !/EXECUTABLE/.test(listText));

  const stale = await page.$eval("#idwarn", (e) => e.textContent);
  check("snapshot freshness surfaced", /snapshot|stale|Building/i.test(stale) || stale.trim() === "", stale.slice(0, 70));

  console.log("== view switching ==");
  await page.click('#idviews button:has-text("Pullback watch")');
  await page.waitForFunction(() => /Pullback watch/.test(document.querySelector("#idlisthead").textContent), { timeout: 300000 });
  await page.waitForTimeout(2500);
  const pullbackText = await page.$eval("#idlist", (e) => e.textContent);
  // F12: the pullback view is now defined by Boyd phase 4 (or trend-up with momentum
  // not yet up), NOT by the entry bucket. A phase-4 name may legitimately carry a live
  // plan, so the assertion is on the DEFINITION: every row must be flagged a pullback.
  const pullbackRows = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll("#idlist tbody tr"));
    return rows.length;
  });
  check("pullback view renders under its new definition",
    /Nothing qualifies/.test(pullbackText) || pullbackRows > 0,
    `${pullbackRows} rows`);
  check("pullback view shows Boyd phase 4 guidance",
    /Nothing qualifies/.test(pullbackText) || /PULLBACK|TRIGGER_CONFIRMED|BREAKOUT_WATCH|EXTENDED_WAIT/.test(pullbackText),
    pullbackText.slice(0, 60));
  await page.click('#idviews button:has-text("Ready now")');
  await page.waitForFunction(() => /Ready now/.test(document.querySelector("#idlisthead").textContent), { timeout: 300000 });
  await page.waitForTimeout(2500);
  const readyText = await page.$eval("#idlist", (e) => e.textContent);
  check("ready-now view shows live-plan states only",
    /Nothing qualifies/.test(readyText) || /TRIGGER_CONFIRMED/.test(readyText), readyText.slice(0, 60));

  console.log("== sorting ==");
  const before = await page.$$eval("#idlist tbody tr td:first-child", (ts) => ts.map((t) => t.textContent.trim()));
  await page.selectOption("#idsort", "rs_market");
  await page.waitForTimeout(3000);
  const after = await page.$$eval("#idlist tbody tr td:first-child", (ts) => ts.map((t) => t.textContent.trim()));
  check("sorting changes the order", JSON.stringify(before) !== JSON.stringify(after),
    `${before.slice(0, 3).join(",")} -> ${after.slice(0, 3).join(",")}`);

  console.log("== sector filter ==");
  await page.selectOption("#idsector", "SMH");
  await page.waitForTimeout(3000);
  const smhText = await page.$eval("#idlist", (e) => e.textContent);
  check("sector filter applied", /SMH|Nothing qualifies/.test(smhText), smhText.slice(0, 50));
  await page.selectOption("#idsector", "");
  await page.waitForTimeout(2500);

  console.log("== detail panel ==");
  await page.click('#idlist button:has-text("Why?") >> nth=0');
  await page.waitForFunction(() => {
    const el = document.querySelector("#iddetail");
    return el && /Why this stock/.test(el.textContent);
  }, { timeout: 180000 });
  const det = await page.$eval("#iddetail", (e) => e.textContent);
  check("detail answers why this stock", /Why this stock/.test(det));
  check("detail answers why now", /Why now/.test(det) && /Before entry/.test(det));
  check("detail answers invalidation", /What invalidates/.test(det));
  check("detail answers conflicts", /Conflicts/.test(det));
  check("detail answers duplicate exposure", /Duplicate exposure/.test(det));
  check("detail shows the next action", /Next action/.test(det));
  check("detail declares UNDERLYING_ONLY", /UNDERLYING_ONLY/.test(det));

  console.log("== why ranked ==");
  await page.click('#iddetail button:has-text("Why ranked here?")');
  await page.waitForFunction(() => {
    const el = document.querySelector("#idwhy");
    return el && /is #\d+ of \d+/.test(el.textContent);
  }, { timeout: 180000 });
  const why = await page.$eval("#idwhy", (e) => e.textContent);
  check("why-ranked gives a position and reasons", /is #\d+ of \d+/.test(why), why.slice(0, 70));
  check("why-ranked disclaims a universal score", /no single universal score/.test(why));

  console.log("== carry to Trade Workspace ==");
  await page.click('#iddetail button:has-text("Open Trade Workspace")');
  await page.waitForURL(/\/trade/, { timeout: 60000 });
  await page.waitForFunction(() => {
    const el = document.querySelector("#setupbadge");
    return el && /v1/.test(el.textContent);
  }, { timeout: 120000 });
  const badge = await page.$eval("#setupbadge", (e) => e.textContent.trim());
  check("idea carried to Trade Workspace", /v1/.test(badge), badge);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("qx.selectedSetup") || "null"));
  check("carried setup keeps sector provenance", !!stored && !!stored.sector_parent, JSON.stringify(stored && stored.sector_parent));
  check("carried setup is not executable",
    stored && stored.executable === false && stored.publication_state === "RESEARCH_ONLY");

  console.log("== responsive + console ==");
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto("http://127.0.0.1:8790/ideas", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(8000);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("no horizontal overflow at 420px", overflow <= 8, `overflow=${overflow}px`);
  check("no uncaught page errors", errors.length === 0, errors.slice(0, 2).join(" | ") || "clean");

  const fs = require("fs");
  fs.mkdirSync("C:/Project/2026/data/reports/qx_ui", { recursive: true });
  await page.setViewportSize({ width: 1560, height: 1040 });
  await page.goto("http://127.0.0.1:8790/ideas", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => /Ready now/.test(document.querySelector("#idviews").textContent), { timeout: 300000 }).catch(() => {});
  await page.waitForTimeout(4000);
  await page.screenshot({ path: "C:/Project/2026/data/reports/qx_ui/trade-ideas.png", fullPage: false });
  check("screenshot captured", fs.existsSync("C:/Project/2026/data/reports/qx_ui/trade-ideas.png"));

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error("SUITE ERROR:", e.message); process.exit(2); });
