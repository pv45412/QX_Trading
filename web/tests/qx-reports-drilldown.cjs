// Scratch: verify the new reports UI (split + month->day drill-down) in a browser.
const { chromium } = require("playwright");

let pass = 0, fail = 0;
function check(label, cond, extra = "") {
  if (cond) { pass++; console.log(`  PASS  ${label} ${extra}`); }
  else { fail++; console.log(`  FAIL  ${label} ${extra}`); }
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  page.setDefaultTimeout(600000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("http://127.0.0.1:8790/reports", { waitUntil: "domcontentloaded" });
  // The broker read can transiently 503; retry until a report body is present.
  for (let attempt = 0; attempt < 6; attempt += 1) {
    if (attempt > 0) { try { await page.click("text=Refresh", { timeout: 20000 }); } catch (e) { /* ignore */ } }
    const ready = await page.waitForFunction(() => {
      const el = document.querySelector("#body");
      if (!el) return false;
      return /Options vs Stocks/.test(el.textContent) || /Broker read failed/.test(el.textContent);
    }, { timeout: 240000 }).then(() => true).catch(() => false);
    if (!ready) continue;
    const broke = await page.$eval("#body", (e) => /Broker read failed/.test(e.textContent));
    if (!broke) break;
    console.log("  INFO  upstream broker error, retrying…");
    await page.waitForTimeout(20000);
  }

  // Drill-down assertions target a single account (the __ALL__ view renders one
  // independent block per account, so the namespaced ids differ).
  await page.selectOption("#acct", { index: 1 });
  await page.click("text=Refresh");
  await page.waitForFunction(() => !!document.getElementById("one-md-0"), { timeout: 240000 });

  const body = await page.$eval("#body", (e) => e.textContent);
  check("split card renders", /Options vs Stocks/.test(body));
  check("split shows Options and Stocks KPIs", /Options/.test(body) && /Stocks/.test(body));
  check("split table has type rows", /options/.test(body) && /stocks/.test(body));
  check("monthly drill-down card renders", /click a month to drill into days/.test(body));
  check("daily section renders", /Daily realized P&L/.test(body));

  const splitKpis = await page.$$eval("#one-split > .kpis > .kpi", (ks) => ks.map((k) => k.textContent.trim()));
  check("five split KPIs", splitKpis.length === 5, `${splitKpis.length}: ${JSON.stringify(splitKpis.slice(0, 2))}`);

  const splitRows = await page.$$eval("#one-split tbody tr", (rs) => rs.length);
  check("split table rows", splitRows >= 3, `${splitRows} rows`);

  const monthRows = await page.$$eval("#body tr[onclick^='toggleMonth']", (rs) => rs.length);
  check("month rows rendered", monthRows >= 1, `${monthRows} months`);

  // Drill down: the handler sits on the month HEADER row; the detail row below
  // it carries the id and starts hidden.
  const headerRow = await page.$("#body tr[onclick^='toggleMonth']");
  check("month rows are clickable", !!headerRow);
  if (headerRow) {
    const detailBefore = await page.$eval("#one-md-0", (e) => e.style.display);
    const caretBefore = await page.$eval("#one-md-0-c", (e) => e.innerHTML);
    await headerRow.click();
    await page.waitForTimeout(600);
    const detailAfter = await page.$eval("#one-md-0", (e) => e.style.display);
    check("clicking a month expands its days", detailBefore === "none" && detailAfter !== "none",
      `${detailBefore} -> ${detailAfter}`);
    const caretAfter = await page.$eval("#one-md-0-c", (e) => e.innerHTML);
    check("caret toggles", caretBefore !== caretAfter, `${caretBefore} -> ${caretAfter}`);
    const dayRows = await page.$$eval("#one-md-0 tbody tr", (rs) => rs.length);
    check("expanded month lists day rows", dayRows >= 1, `${dayRows} days`);
    const dayText = await page.$eval("#one-md-0", (e) => e.textContent);
    check("day rows show per-day realized", /20\d\d-\d\d-\d\d/.test(dayText));
    check("expanded month shows options/stocks columns", /Options/.test(dayText) || /opt/i.test(dayText));
    check("expanded month lists symbols", /Symbols traded in/.test(dayText) === true);

    await headerRow.click();
    await page.waitForTimeout(500);
    const collapsed = await page.$eval("#one-md-0", (e) => e.style.display === "none");
    check("clicking again collapses the month", collapsed === true);
  }

  const daySection = await page.$$eval("#body .card", (cs) => cs.map((c) => c.textContent).join(" "));
  check("all-days table present", /Daily realized P&L/.test(daySection));

  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | ") || "clean");

  const fs = require("fs");
  fs.mkdirSync("C:/Project/2026/data/reports/qx_ui", { recursive: true });
  await page.screenshot({ path: "C:/Project/2026/data/reports/qx_ui/reports-drilldown.png", fullPage: true });
  console.log("  INFO  screenshot written");
  check("screenshot captured", fs.existsSync("C:/Project/2026/data/reports/qx_ui/reports-drilldown.png"));

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error("SUITE ERROR:", e.message); process.exit(2); });
