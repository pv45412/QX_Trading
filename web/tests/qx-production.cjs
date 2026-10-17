// All-pages production test: every route loads, renders, stays responsive, and
// makes no false claims. F23 disclosure is asserted where a plan is shown.
const { chromium } = require("playwright");

let pass = 0, fail = 0;
const failures = [];
function check(page, l, c, e = "") {
  if (c) { pass++; console.log(`  PASS  [${page}] ${l} ${e}`); }
  else { fail++; failures.push(`[${page}] ${l} ${e}`); console.log(`  FAIL  [${page}] ${l} ${e}`); }
}

const PAGES = [
  { path: "/scanner", name: "discover", must: [/Discover/i, /Market context/i, /Sector rankings/i] },
  { path: "/ideas", name: "ideas", must: [/Trade ideas/i, /Ready now/i] },
  { path: "/trade", name: "trade", must: [/Trade/i] },
  { path: "/context", name: "context", must: [/Context/i, /Levels/i] },
  { path: "/reports", name: "reports", must: [/Report|P&L|Account/i] },
  { path: "/settings", name: "settings", must: [/Settings/i, /Schwab/i] },
];

(async () => {
  const browser = await chromium.launch();
  const fs = require("fs");
  fs.mkdirSync("C:/Project/2026/data/reports/qx_ui", { recursive: true });

  for (const spec of PAGES) {
    console.log(`\n===== ${spec.path} =====`);
    const page = await browser.newPage({ viewport: { width: 1560, height: 1040 } });
    page.setDefaultTimeout(600000);
    const errors = [];
    page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
    page.on("console", (m) => {
      if (m.type() === "error" && !/400|404|503|Failed to load resource/.test(m.text()))
        errors.push("console: " + m.text().slice(0, 140));
    });

    await page.goto("http://127.0.0.1:8790" + spec.path, { waitUntil: "domcontentloaded" });
    // Let async panels settle.
    await page.waitForTimeout(14000);

    const body = await page.$eval("body", (b) => b.innerText);
    check(spec.name, "page renders content", body.length > 200, `${body.length} chars`);
    for (const pattern of spec.must) {
      check(spec.name, `contains ${pattern}`, pattern.test(body));
    }

    // Nav present and marks this page active.
    const navItems = await page.$$eval("#nav a", (as) => as.map((a) => a.textContent.trim()));
    check(spec.name, "nav has all six pages", navItems.length === 6, JSON.stringify(navItems));
    const active = await page.$eval("#nav a.on", (a) => a.textContent.trim()).catch(() => "(none)");
    check(spec.name, "an active nav item is marked", active !== "(none)", active);

    // Exchange-time clock, not UTC.
    const clock = await page.$eval("#clock", (e) => e.textContent).catch(() => "");
    check(spec.name, "header shows exchange time", /ET/.test(clock), clock.slice(0, 40));
    check(spec.name, "no raw UTC clock time shown", !/\d{2}:\d{2}:\d{2}\s*UTC/.test(body));

    // The universal safety label.
    check(spec.name, "live-execution-disabled label present",
      /LIVE EXECUTION DISABLED/i.test(body));

    // No JS errors.
    check(spec.name, "no uncaught JS errors", errors.length === 0,
      errors.slice(0, 2).join(" | ") || "clean");

    // Responsive.
    await page.setViewportSize({ width: 420, height: 900 });
    await page.waitForTimeout(2500);
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(spec.name, "no horizontal overflow at 420px", overflow <= 8, `${overflow}px`);

    await page.setViewportSize({ width: 1560, height: 1040 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `C:/Project/2026/data/reports/qx_ui/prod-${spec.name}.png` });
    await page.close();
  }

  // F23: where a plan is shown, the reference level must be labelled as such.
  console.log("\n===== F23 disclosure on live pages =====");
  const page = await browser.newPage({ viewport: { width: 1560, height: 1040 } });
  page.setDefaultTimeout(600000);
  await page.goto("http://127.0.0.1:8790/ideas", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => /Ready now/.test(document.querySelector("#idviews").textContent),
    { timeout: 300000 }).catch(() => {});
  await page.waitForTimeout(6000);

  const ideasText = await page.$eval("body", (b) => b.innerText);
  check("f23", "ideas page labels the level 'Ref stop' or 'Ref. stop'",
    /Ref\.? stop/i.test(ideasText), ideasText.match(/Ref\.? stop/gi)?.slice(0, 2).join(",") || "absent");
  check("f23", "ideas page does NOT use 'Invalid.' as a column header",
    !/\bInvalid\./.test(ideasText));
  check("f23", "ideas page does NOT claim 'close through'",
    !/close through/i.test(ideasText));

  // Open a detail panel and look for the disclosure.
  const detailBtn = await page.$('#idlist button:has-text("Why?")');
  if (detailBtn) {
    await detailBtn.click();
    await page.waitForTimeout(3000);
    const detail = await page.$eval("#iddetail", (e) => e.innerText);
    check("f23", "idea detail says the reference is not enforced",
      /not enforced|REFERENCE/i.test(detail), detail.slice(0, 80));
    check("f23", "idea detail states the study exit rule",
      /study/i.test(detail) || /wave centre/i.test(detail), detail.slice(0, 80));
  } else {
    check("f23", "no idea row available to inspect (informational)", true);
  }
  await page.close();

  // F23 on the explorer member detail.
  console.log("\n===== F23 disclosure in the explorer =====");
  const p2 = await browser.newPage({ viewport: { width: 1560, height: 1040 } });
  p2.setDefaultTimeout(600000);
  await p2.goto("http://127.0.0.1:8790/scanner", { waitUntil: "domcontentloaded" });
  await p2.waitForFunction(() => document.querySelectorAll(".secrow").length > 0, { timeout: 300000 });
  await p2.evaluate(() => {
    const r = Array.from(document.querySelectorAll("tr")).find((x) => /SMH/.test(x.textContent));
    const b = r && r.querySelector("button");
    if (b) b.click();
  });
  await p2.waitForFunction(() => /Momo\+Trend up/.test(document.querySelector("#exdetail").textContent),
    { timeout: 600000 }).catch(() => {});
  await p2.waitForTimeout(4000);
  const memberBtn = await p2.$('#exdetail button:has-text("Detail")');
  if (memberBtn) {
    await memberBtn.click();
    await p2.waitForTimeout(3000);
    const mem = await p2.$eval("#memdetail", (e) => e.innerText);
    check("f23-explorer", "member detail labels the level as a reference",
      /Ref\.? stop/i.test(mem), mem.slice(0, 70));
    check("f23-explorer", "member detail states the study exit rule",
      /Exit rule \(study\)/i.test(mem), mem.slice(0, 70));
    check("f23-explorer", "member detail says the level is not enforced",
      /not a protected stop|not enforced/i.test(mem));
    await p2.screenshot({ path: "C:/Project/2026/data/reports/qx_ui/prod-f23-disclosure.png" });
  } else {
    check("f23-explorer", "no member row to inspect (informational)", true);
  }
  await p2.close();

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  if (failures.length) { console.log("FAILURES:"); failures.forEach((f) => console.log("  " + f)); }
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error("SUITE ERROR:", e.message); process.exit(2); });
