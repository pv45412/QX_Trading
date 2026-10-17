// Scratch: inspect the live DOM around the chart and the notes panel.
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
  page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE ERROR:", m.text()); });

  await page.goto("http://127.0.0.1:8790/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("#results tbody tr").length > 0, { timeout: 240000 });
  await page.click("#results tbody tr");
  await page.waitForFunction(() => /Score breakdown/.test(document.querySelector("#sel").textContent), { timeout: 120000 });
  await page.waitForTimeout(2500);

  console.log("hasChartbox:", await page.evaluate(() => !!document.getElementById("chartbox")));
  console.log("chartbox html:", await page.evaluate(() => {
    const e = document.getElementById("chartbox");
    return e ? e.innerHTML.slice(0, 240) : "(missing)";
  }));
  console.log("svg count:", await page.evaluate(() => document.querySelectorAll("#sel svg").length));
  console.log("path count:", await page.evaluate(() => document.querySelectorAll("#sel svg path").length));
  console.log("legend:", await page.evaluate(() => {
    const e = document.getElementById("chartlegend");
    return e ? e.textContent : "(missing)";
  }));
  console.log("sparkline type:", await page.evaluate(() => typeof sparkline));
  console.log("CHART obj:", await page.evaluate(() => {
    try { return JSON.stringify(CHART).slice(0, 160); } catch (e) { return "err " + e.message; }
  }));
  console.log("SELECTED:", await page.evaluate(() => {
    try { return JSON.stringify({ s: SELECTED && SELECTED.symbol, e: SELECTED && SELECTED.entry }); }
    catch (e) { return "err " + e.message; }
  }));
  console.log("direct chart fetch:", await page.evaluate(async () => {
    const r = await fetch("/api/chart?symbol=SPY&timeframe=1d");
    const j = await r.json();
    return "closes=" + (j.closes ? j.closes.length : "none") + " src=" + j.source;
  }));

  await browser.close();
})().catch((e) => { console.error("ERR", e.message); process.exit(2); });
