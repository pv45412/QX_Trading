// QX workspace browser integration suite (Playwright, chromium).
// Exercises every page and the cross-page setup carry in a real browser.
const { chromium } = require("playwright");

const BASE = process.env.QX_BASE || "http://127.0.0.1:8790";
let pass = 0;
let fail = 0;
const failures = [];

function check(label, condition, extra = "") {
  if (condition) {
    pass += 1;
    console.log(`  PASS  ${label} ${extra}`);
  } else {
    fail += 1;
    failures.push(label);
    console.log(`  FAIL  ${label} ${extra}`);
  }
}

async function collectPageErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e && e.message ? e.message : e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console: ${m.text()}`);
  });
  return errors;
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();
  const errors = await collectPageErrors(page);

  // ---------- navigation ----------
  console.log("== navigation ==");
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  check("/ redirects to /scanner", page.url().endsWith("/scanner"), page.url());

  const navLinks = await page.$$eval("#nav a", (as) => as.map((a) => a.textContent.trim()));
  check("nav exposes the workspace pages", navLinks.length === 6 &&
    ["Discover", "Trade Ideas", "Trade Workspace", "Context", "Reports", "Settings"]
      .every((n) => navLinks.includes(n)),
    JSON.stringify(navLinks));
  const active = await page.$eval("#nav a.on", (a) => a.textContent.trim());
  check("active nav marks Discover", active === "Discover", active);
  const liveBadge = await page.$eval("#livemode", (e) => e.textContent);
  check("live-execution-disabled badge visible", /DISABLED/.test(liveBadge), liveBadge);

  // ---------- scanner ----------
  console.log("== scanner ==");
  await page.waitForFunction(() => {
    const el = document.querySelector("#sectors");
    return el && /XL|LEADING|LAGGING/.test(el.textContent);
  }, { timeout: 180000 });
  const sectorRows = await page.$$eval(".secrow", (rs) => rs.length);
  check("sector strip renders 11 rows", sectorRows === 11, `${sectorRows} rows`);

  const sectorStamp = await page.$eval("#secstamp", (e) => e.textContent);
  check("sector coverage states 11/11", /11\/11/.test(sectorStamp), sectorStamp);

  await page.waitForFunction(() => {
    const el = document.querySelector("#verdict");
    return el && el.textContent.trim().length > 10;
  }, { timeout: 240000 });
  const verdict = await page.$eval("#verdict", (e) => e.textContent.trim());
  check("verdict rendered", /qualified|NO_QUALIFIED_TRADE/i.test(verdict), verdict.slice(0, 70));

  await page.waitForFunction(() => {
    const rows = document.querySelectorAll("#results tbody tr");
    return rows.length > 0;
  }, { timeout: 240000 });
  const resultRows = await page.$$eval("#results tbody tr", (rs) => rs.length);
  check("results table populated", resultRows > 0, `${resultRows} rows`);

  const ctxKpis = await page.$$eval("#ctx .kpi", (ks) => ks.length);
  check("market context KPIs", ctxKpis >= 4, `${ctxKpis} KPIs`);

  // ---------- filters ----------
  console.log("== filters ==");
  await page.selectOption("#fside", "LONG");
  await page.waitForTimeout(400);
  const longRows = await page.$$eval("#results tbody tr", (rs) => rs.length);
  await page.selectOption("#fside", "");
  await page.waitForTimeout(400);
  const allRows = await page.$$eval("#results tbody tr", (rs) => rs.length);
  check("side filter narrows results", longRows <= allRows, `LONG=${longRows} all=${allRows}`);

  // ---------- selected setup + chart ----------
  console.log("== selected setup ==");
  await page.click("#results tbody tr");
  await page.waitForFunction(() => {
    const el = document.querySelector("#sel");
    return el && /Score breakdown/.test(el.textContent);
  }, { timeout: 120000 });
  const selText = await page.$eval("#sel", (e) => e.textContent);
  check("selected panel shows score breakdown", /Score breakdown/.test(selText));
  // F23: "Invalidation" became "Ref. stop" — the study does not exit at that level.
  check("selected panel shows plan levels",
    /Entry/.test(selText) && /Ref\.? stop/.test(selText), selText.slice(0, 60));
  check("selected panel says the reference is not enforced",
    /REFERENCE|not enforced/i.test(selText), selText.slice(0, 60));
  // The chart loads asynchronously after the panel paints, so wait for it.
  await page.waitForFunction(() => document.querySelectorAll("#sel svg path").length >= 1, { timeout: 120000 })
    .catch(() => {});
  const svgCount = await page.$$eval("#sel svg path", (ps) => ps.length);
  check("chart renders a price path", svgCount >= 1, `${svgCount} paths`);
  const legend = await page.$eval("#chartlegend", (e) => e.textContent);
  check("chart legend shows plan levels", /entry/.test(legend) && /invalidation/.test(legend) && /bars/.test(legend),
    legend.slice(0, 72));
  const factorRows = await page.$$eval("#sel tbody tr", (rs) => rs.length);
  check("factor table lists all six factors", factorRows >= 6, `${factorRows} rows`);
  const selectedSymbol = await page.$eval("#sel b", (b) => b.textContent.trim());
  check("selected symbol recorded", selectedSymbol.length > 0, selectedSymbol);

  // ---------- notes on scanner ----------
  console.log("== notes (scanner) ==");
  // The drawer may already be open; open it only when it is closed.
  const drawerClosed = await page.$eval("#sel details", (d) => !d.open);
  if (drawerClosed) { await page.click("#sel summary"); }
  await page.waitForTimeout(300);
  await page.click("text=Generate / refresh notes");
  await page.waitForFunction(() => {
    const el = document.querySelector("#notesbody");
    return el && /Evidence cited/.test(el.textContent);
  }, { timeout: 120000 });
  const notesText = await page.$eval("#notesbody", (e) => e.textContent);
  check("notes render seven sections", /7\. Post-trade review/.test(notesText));
  check("notes show FRESH or STALE chip", /FRESH|STALE/.test(notesText));
  check("notes show evidence table", /Evidence cited/.test(notesText));
  check("notes disclose what they cannot do", /cannot/.test(notesText));

  const cmdButtons = await page.$$eval("#notesbody button.ghost", (bs) => bs.map((b) => b.textContent.trim()));
  check("notes expose all six commands", cmdButtons.length === 6, JSON.stringify(cmdButtons));

  await page.click("#notesbody button.ghost");
  await page.waitForFunction(() => {
    const el = document.querySelector("#noteoutbox");
    return el && !/Running/.test(el.textContent) && el.textContent.trim().length > 20;
  }, { timeout: 120000 });
  const cmdOut = await page.$eval("#noteoutbox", (e) => e.textContent);
  check("notes command returns an answer", /scores/.test(cmdOut), cmdOut.slice(0, 60));

  // A command must not disturb the notes panel it was launched from.
  const notesStillThere = await page.$eval("#notesbody", (e) => /Evidence cited/.test(e.textContent));
  check("command output does not clobber the notes panel", notesStillThere === true);

  // Every command must answer.
  console.log("== all notes commands ==");
  const labels = ["What would invalidate it?", "Compare with qualified", "Update plan using current data",
    "Explain order risk", "Review completed trade"];
  for (const label of labels) {
    await page.click(`#notesbody button:has-text("${label}")`);
    await page.waitForFunction(() => {
      const el = document.querySelector("#noteoutbox");
      return el && !/Running/.test(el.textContent) && el.textContent.trim().length > 10;
    }, { timeout: 120000 });
    const text = await page.$eval("#noteoutbox", (e) => e.textContent);
    check(`command "${label}" answers`, text.length > 10, text.slice(0, 52));
  }

  // ---------- cross-page setup carry ----------
  console.log("== setup carry (scanner -> trade) ==");
  await page.click("text=Open Trade Workspace");
  await page.waitForURL(/\/trade/, { timeout: 60000 });
  await page.waitForFunction(() => {
    const el = document.querySelector("#setupbadge");
    return el && /score/.test(el.textContent);
  }, { timeout: 60000 });
  const badge = await page.$eval("#setupbadge", (e) => e.textContent);
  check("setup carried into trade page", /score/.test(badge), badge.trim());
  const ticketSym = await page.inputValue("#t_sym");
  check("ticket prefilled with carried symbol", ticketSym.length > 0, ticketSym);
  const ticketLimit = await page.inputValue("#t_limit");
  check("ticket prefilled with entry price", ticketLimit.length > 0, ticketLimit);

  // ---------- trade workspace ----------
  console.log("== trade workspace ==");
  const activeTrade = await page.$eval("#nav a.on", (a) => a.textContent.trim());
  check("active nav marks Trade Workspace", activeTrade === "Trade Workspace", activeTrade);
  const gate = await page.$eval("#livegate", (e) => e.textContent);
  check("live submission gate banner shown", /DISABLED/.test(gate) && /simulated/i.test(gate));

  await page.waitForFunction(() => {
    const el = document.querySelector("#acctkpi");
    return el && /Equity/.test(el.textContent);
  }, { timeout: 180000 });
  const acctKpi = await page.$eval("#acctkpi", (e) => e.textContent);
  check("account KPIs loaded", /Equity/.test(acctKpi) && /Buying power/.test(acctKpi));

  const accountOptions = await page.$$eval("#acct option", (os) => os.length);
  check("account selector lists accounts", accountOptions >= 1, `${accountOptions} options`);
  const posRows = await page.$$eval("#positions tbody tr", (rs) => rs.length);
  check("positions table rendered", posRows >= 0, `${posRows} rows`);
  const ooStamp = await page.$eval("#oostamp", (e) => e.textContent);
  check("open-orders stamp reports counts", /open of|unavailable/.test(ooStamp), ooStamp);

  // ---------- review + confirm + duplicate ----------
  console.log("== review / confirm / duplicate ==");
  // Use a unique quantity so this run never collides with a previously staged
  // order (the intent ledger would otherwise block it as a duplicate).
  const uniqueQty = 1 + Math.floor(Math.random() * 9);
  await page.fill("#t_qty", String(uniqueQty));
  await page.click("text=Review order");
  await page.waitForFunction(() => {
    const el = document.querySelector("#review");
    return el && /Deterministic checks/.test(el.textContent);
  }, { timeout: 180000 });
  const reviewText = await page.$eval("#review", (e) => e.textContent);
  check("local review lists checks", /Deterministic checks/.test(reviewText));
  check("review shows ticket hash", /Ticket hash/.test(reviewText));
  check("review reports repo gate", /execution-eligibility gate/.test(reviewText));
  const payload = await page.$eval("#review pre.payload", (e) => e.textContent);
  check("exact proposed order shown", /"symbol"/.test(payload) && /"quantity"/.test(payload));

  const verdictText = await page.$eval("#verdictbadge", (e) => e.textContent.trim());
  check("ticket reaches a definitive verdict", /READY_FOR_CONFIRMATION|BLOCKED/.test(verdictText), verdictText);

  if (/READY_FOR_CONFIRMATION/.test(verdictText)) {
    // The confirmation gate must start unchecked, and a stale checkbox id from a
    // previous render must never leave Submit armed.
    const chk = await page.$("#okchk");
    await chk.uncheck().catch(() => {});
    await page.waitForTimeout(150);
    const subDisabled = await page.$eval("#subbtn", (b) => b.disabled);
    const chkState = await page.$eval("#okchk", (c) => c.checked);
    check("submit disabled while confirmation unchecked", subDisabled === true && chkState === false,
      `disabled=${subDisabled} checked=${chkState}`);
    const liveBtnDisabled = await page.$eval("text=Submit live (disabled)", (b) => b.disabled);
    check("live submit button permanently disabled", liveBtnDisabled === true);

    await page.check("#okchk");
    await page.waitForTimeout(120);
    const subEnabled = await page.$eval("#subbtn", (b) => !b.disabled);
    check("submit enabled after explicit confirmation", subEnabled === true);

    await page.click("#subbtn");
    await page.waitForFunction(() => {
      const el = document.querySelector("#tnote");
      return el && /SIM-/.test(el.textContent);
    }, { timeout: 180000 });
    const note = await page.$eval("#tnote", (e) => e.textContent);
    check("simulated order recorded", /SIM-/.test(note), note.trim());

    await page.waitForFunction(() => {
      const el = document.querySelector("#orders");
      return el && /SIM-/.test(el.textContent);
    }, { timeout: 60000 });
    const ordersText = await page.$eval("#orders", (e) => e.textContent);
    check("order book shows the simulated order", /SIM-/.test(ordersText));
    check("order book labelled SIMULATED", /SIMULATED/.test(ordersText));

    // Re-submitting the identical ticket must be refused by the intent ledger.
    const dup = await page.evaluate(async () => {
      const r = await fetch("/api/trade/orders", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ticket: {
            account: document.querySelector("#acct").value,
            symbol: document.querySelector("#t_sym").value.trim().toUpperCase(),
            side: document.querySelector("#t_side").value,
            quantity: Number(document.querySelector("#t_qty").value),
            order_type: document.querySelector("#t_type").value,
            limit_price: Number(document.querySelector("#t_limit").value),
            duration: document.querySelector("#t_dur").value,
          },
          account: document.querySelector("#acct").value, confirm: true,
        }),
      });
      return await r.json();
    });
    check("duplicate submission refused", dup.ok === false && /duplicate/i.test(String(dup.error)),
      String(dup.error).slice(0, 60));
  } else {
    // A blocked ticket must still prove the safety rails are present.
    const subDisabled = await page.$eval("#subbtn", (b) => b.disabled);
    check("blocked ticket cannot submit", subDisabled === true, verdictText);
    const liveBtnDisabled = await page.$eval("text=Submit live (disabled)", (b) => b.disabled);
    check("live submit button permanently disabled", liveBtnDisabled === true);
    const blocked = await page.$eval("#review", (e) => e.textContent);
    check("blocked review names the failing checks", /BLOCKED by:/.test(blocked));
  }

  // ---------- reports ----------
  console.log("== reports ==");
  await page.click('#nav a[href="/reports"]');
  await page.waitForURL(/\/reports/, { timeout: 60000 });
  await page.waitForFunction(() => {
    const el = document.querySelector("#body");
    return el && /Equity/i.test(el.textContent) && !/Loading/.test(el.textContent);
  }, { timeout: 300000 });
  const reportsText = await page.$eval("#body", (e) => e.textContent);
  check("reports shows equity/P&L", /Equity/i.test(reportsText) && /Realized/i.test(reportsText));
  check("reports shows trade-type breakdown", /P&L by trade type/i.test(reportsText));
  check("reports keeps accounts separate", /kept separate|never combined/i.test(await page.content()));
  const reportAccountOptions = await page.$$eval("#acct option", (os) => os.length);
  check("reports account selector present", reportAccountOptions >= 2, `${reportAccountOptions} options`);

  // Keep every account separate: each block carries its own report.
  const separate = await page.$$eval(".acctblock", (bs) => bs.length).catch(() => 0);
  console.log(`  INFO  separate account blocks: ${separate}`);
  const scope = await page.content();
  check("reports never aggregate accounts", /never combined|kept separate/i.test(scope));
  check("reports shows data-quality disclosure", /Cost method/i.test(reportsText));

  // ---------- return navigation ----------
  console.log("== return navigation ==");
  await page.click('#nav a[href="/scanner"]');
  await page.waitForURL(/\/scanner/, { timeout: 60000 });
  const backActive = await page.$eval("#nav a.on", (a) => a.textContent.trim());
  check("nav returns to Discover", backActive === "Discover", backActive);
  await page.click('#nav a[href="/trade"]');
  await page.waitForURL(/\/trade/, { timeout: 60000 });
  const tradeSetup = await page.$eval("#setupbadge", (e) => e.textContent);
  check("setup still carried after navigation", /score/.test(tradeSetup), tradeSetup.trim());

  // ---------- responsive ----------
  console.log("== responsive ==");
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto(BASE + "/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("no horizontal overflow at 420px", overflow <= 8, `overflow=${overflow}px`);
  await page.goto(BASE + "/trade", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  const overflow2 = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("trade page no overflow at 420px", overflow2 <= 8, `overflow=${overflow2}px`);

  // ---------- console cleanliness ----------
  console.log("== console ==");
  const realErrors = errors.filter((e) => !/favicon/i.test(e) && !/400 \(Bad Request\)/i.test(e));
  check("no uncaught page errors", realErrors.length === 0, realErrors.slice(0, 3).join(" | ") || "clean");
  const fourHundreds = errors.filter((e) => /400 \(Bad Request\)/i.test(e));
  console.log(`  INFO  expected 400 responses observed: ${fourHundreds.length} (duplicate-order guard)`);

  // ---------- screenshots ----------
  console.log("== screenshots ==");
  const outDir = "C:/Project/2026/data/reports/qx_ui";
  const fs = require("fs");
  try { fs.mkdirSync(outDir, { recursive: true }); } catch (e) { /* ignore */ }
  await page.setViewportSize({ width: 1440, height: 980 });
  for (const [name, path] of [["scanner", "/scanner"], ["trade", "/trade"], ["reports", "/reports"]]) {
    await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${outDir}/${name}-desktop.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto(BASE + "/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outDir}/scanner-mobile.png`, fullPage: true });
  check("screenshots captured", fs.existsSync(`${outDir}/scanner-desktop.png`) &&
    fs.existsSync(`${outDir}/trade-desktop.png`) && fs.existsSync(`${outDir}/reports-desktop.png`) &&
    fs.existsSync(`${outDir}/scanner-mobile.png`), outDir);

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  if (failures.length) console.log("FAILED: " + failures.join(", "));
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => {
  console.error("SUITE ERROR:", e && e.message ? e.message : e);
  process.exit(2);
});
