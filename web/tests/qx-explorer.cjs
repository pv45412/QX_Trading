// Browser integration test for the Discover explorer.
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

  console.log("== discover page ==");
  await page.goto("http://127.0.0.1:8790/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => {
    const el = document.querySelector("#excatalog");
    return el && /Explore/.test(el.textContent);
  }, { timeout: 300000 });
  const cat = await page.$eval("#excatalog", (e) => e.textContent);
  check("sector catalog rendered", /Sectors \(11\)/.test(cat) && /Industries/.test(cat), cat.slice(0, 50));
  check("SMH listed as an industry", /SMH/.test(cat));
  const universeOpts = await page.$$eval("#exuniverse option", (os) => os.map((o) => o.textContent.slice(0, 18)));
  check("both universes offered", universeOpts.length === 2, JSON.stringify(universeOpts));

  console.log("== click SMH to explore ==");
  await page.click('button:has-text("Explore →") >> nth=11').catch(async () => {
    // fall back: click the Explore button on the SMH row
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      const smhRow = Array.from(document.querySelectorAll("tr")).find((r) => /SMH/.test(r.textContent));
      const b = smhRow && smhRow.querySelector("button");
      if (b) b.click();
    });
  });
  await page.waitForFunction(() => {
    const el = document.querySelector("#exdetail");
    return el && /Momo\+Trend up/.test(el.textContent);
  }, { timeout: 600000 });
  const detail = await page.$eval("#exdetail", (e) => e.textContent);
  check("explorer loaded SMH", /SMH/.test(detail));
  check("breadth shown", /Momo\+Trend up/.test(detail) && /Weight covered/.test(detail));
  check("universe disclosed", /Universe ETF_REPORTED_TOP_HOLDINGS/.test(detail)
    && /stockanalysis/.test(detail), (detail.match(/Universe[^·]{0,46}/) || [""])[0]);
  check("holdings date honesty", /retrieval time is not a holdings date/.test(detail));
  check("rule versions shown", /tops_multitrend_v4/.test(detail) && /qx_master_auto_fast/.test(detail));

  const memberRows = await page.$$eval("#exdetail tbody tr", (rs) => rs.length);
  check("member table populated", memberRows > 0, `${memberRows} rows`);
  const momoChips = await page.$$eval("#exdetail .chip", (cs) => cs.map((c) => c.textContent.trim()));
  check("momentum/trend chips present", momoChips.includes("BULLISH"), JSON.stringify(momoChips.slice(0, 8)));

  console.log("== views ==");
  const viewButtons = await page.$$eval("#exdetail button", (bs) => bs.map((b) => b.textContent.trim()));
  check("all eight views offered", viewButtons.filter((b) => /\(\d+\)/.test(b)).length >= 8,
    `${viewButtons.filter((b) => /\(\d+\)/.test(b)).length} views`);
  await page.click('button:has-text("All members")');
  await page.waitForFunction(() => /showing \d+ of \d+/.test(document.querySelector("#exdetail").textContent), { timeout: 600000 });
  await page.waitForTimeout(2500);
  const allRows = await page.$$eval("#exdetail tbody tr", (rs) => rs.length);
  check("all-members view expands the table", allRows >= memberRows, `all=${allRows} aligned=${memberRows}`);

  console.log("== member detail + notes ==");
  await page.click('#exdetail button:has-text("Detail") >> nth=0');
  await page.waitForFunction(() => {
    const el = document.querySelector("#memdetail");
    return el && /Chase limit/.test(el.textContent);
  }, { timeout: 120000 });
  const mem = await page.$eval("#memdetail", (e) => e.textContent);
  // F23: the level is labelled "Ref. stop" — a REFERENCE the study does not enforce.
  check("detail shows plan levels", /Trigger/.test(mem) && /Ref\.? stop/.test(mem) && /Target/.test(mem));
  check("detail discloses the reference is not enforced",
    /not a protected stop|not enforced|REFERENCE/i.test(mem), mem.slice(0, 60));
  check("detail shows chase limit", /Chase limit/.test(mem));
  check("detail shows RS vs parent and market", /Parent ETF/.test(mem) && /Market \(SPY\)/.test(mem));
  check("no EXECUTABLE claim", !/EXECUTABLE/.test(mem));

  await page.click('#memdetail button:has-text("AI notes")');
  await page.waitForFunction(() => {
    const el = document.querySelector("#membnotes");
    return el && /This note cannot/.test(el.textContent);
  }, { timeout: 180000 });
  const notes = await page.$eval("#membnotes", (e) => e.textContent);
  check("notes generated with evidence", /Momentum and trend are UP|not aligned/.test(notes));
  check("notes state their limits", /cannot:/.test(notes));

  console.log("== carry to Trade Workspace ==");
  await page.click('#memdetail button:has-text("Open Trade Workspace")');
  await page.waitForURL(/\/trade/, { timeout: 60000 });
  await page.waitForFunction(() => {
    const el = document.querySelector("#setupbadge");
    return el && /score|SMH|v1/.test(el.textContent) && !/no setup/.test(el.textContent);
  }, { timeout: 120000 });
  const badge = await page.$eval("#setupbadge", (e) => e.textContent.trim());
  check("setup carried into Trade Workspace", /v1/.test(badge), badge);
  const sym = await page.inputValue("#t_sym");
  check("ticket prefilled with the member symbol", sym.length > 0, sym);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("qx.selectedSetup") || "null"));
  check("identity carries sector provenance", stored && stored.sector_parent === "SMH", JSON.stringify(stored && stored.sector_parent));
  check("carried setup is not executable", stored && stored.executable === false && stored.publication_state === "RESEARCH_ONLY");

  console.log("== responsive ==");
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto("http://127.0.0.1:8790/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(6000);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("discover page no horizontal overflow at 420px", overflow <= 8, `overflow=${overflow}px`);

  check("no uncaught page errors", errors.length === 0, errors.slice(0, 2).join(" | ") || "clean");

  const fs = require("fs");
  fs.mkdirSync("C:/Project/2026/data/reports/qx_ui", { recursive: true });
  await page.setViewportSize({ width: 1560, height: 1040 });
  await page.goto("http://127.0.0.1:8790/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => /Momo\+Trend up/.test(document.body.textContent), { timeout: 600000 }).catch(() => {});
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "C:/Project/2026/data/reports/qx_ui/discover-explorer.png", fullPage: false });
  check("screenshot captured", fs.existsSync("C:/Project/2026/data/reports/qx_ui/discover-explorer.png"));

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error("SUITE ERROR:", e.message); process.exit(2); });
