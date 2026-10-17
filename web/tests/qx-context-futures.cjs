// Browser test: the Context page supports index, futures and ETF symbols.
const { chromium } = require("playwright");

let pass = 0, fail = 0;
function check(l, c, e = "") { if (c) { pass++; console.log(`  PASS  ${l} ${e}`); } else { fail++; console.log(`  FAIL  ${l} ${e}`); } }

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1560, height: 1100 } });
  page.setDefaultTimeout(600000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("http://127.0.0.1:8790/context", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#csym"), { timeout: 60000 });

  console.log("== selector ==");
  const opts = await page.$$eval("#csym option", (os) => os.map((o) => o.value));
  const groups = await page.$$eval("#csym optgroup",
    (gs) => gs.map((g) => `${g.label}:${[...g.querySelectorAll("option")].map((o) => o.value).join(",")}`));
  groups.forEach((g) => console.log("   ", g));
  check("index symbols offered", opts.includes("$SPX"), opts.join(" "));
  check("futures symbols offered", ["/ES", "/NQ", "/CL", "/BTC"].every((s) => opts.includes(s)));
  check("ETF symbols still offered", opts.includes("SPY") && opts.includes("QQQ"));
  check("grouped as Index/Futures/ETF", groups.length === 3, JSON.stringify(groups.map((g) => g.split(":")[0])));

  async function select(symbol) {
    await page.evaluate((s) => {
      const el = document.querySelector("#csym");
      el.value = s;
      el.dispatchEvent(new Event("change"));
    }, symbol);
  }

  console.log("\n== per-symbol behaviour ==");
  for (const symbol of ["$SPX", "/ES", "/NQ", "/CL", "SPY"]) {
    await select(symbol);
    await page.waitForTimeout(26000);
    const state = await page.evaluate(() => ({
      price: (document.querySelector("#lv") || {}).textContent || "",
      gexErr: (document.querySelector("#gx .banner.err") || {}).textContent || "",
      gexTxt: ((document.querySelector("#gx") || {}).textContent || "").replace(/\s+/g, " ").slice(0, 80),
      stamp: (document.querySelector("#lvsrc") || {}).textContent || "",
    }));
    const ok = !state.gexErr;
    console.log(`   ${symbol.padEnd(6)} gex=${ok ? "OK" : "ERR"} ${ok ? state.gexTxt.slice(0, 56) : state.gexErr.slice(0, 56)}`);
    check(`${symbol} resolves levels`, /[\d,]{3}/.test(state.price), state.price.replace(/\s+/g, " ").slice(0, 40));
  }

  // Explicit expectations grounded in the verified API behaviour.
  await select("/ES");
  await page.waitForTimeout(26000);
  const es = await page.evaluate(() => ((document.querySelector("#gx") || {}).textContent || "").replace(/\s+/g, " "));
  check("/ES shows GEX via its cash index (no 400)", !/400|Bad Request/.test(es), es.slice(0, 70));

  await select("/CL");
  await page.waitForTimeout(12000);
  const cl = await page.evaluate(() => ((document.querySelector("#gx") || {}).textContent || "").replace(/\s+/g, " "));
  check("/CL states clearly that no chain exists (not a 400)",
    /no option chain|no cash equivalent/.test(cl), cl.slice(0, 80));

  await select("$SPX");
  await page.waitForTimeout(26000);
  const spx = await page.evaluate(() => ((document.querySelector("#gx .banner.err") || {}).textContent || ""));
  check("$SPX no longer returns the 502/400 chain error", !/Bad Request|502/.test(spx), spx.slice(0, 70));

  check("no uncaught page errors", errors.length === 0, errors.slice(0, 2).join(" | ") || "clean");

  const fs = require("fs");
  fs.mkdirSync("C:/Project/2026/data/reports/qx_ui", { recursive: true });
  await page.screenshot({ path: "C:/Project/2026/data/reports/qx_ui/context-futures.png" });
  check("screenshot captured", fs.existsSync("C:/Project/2026/data/reports/qx_ui/context-futures.png"));

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error("SUITE ERROR:", e.message); process.exit(2); });
