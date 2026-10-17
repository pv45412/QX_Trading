// Scratch: inspect the reports page DOM after load.
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  page.setDefaultTimeout(120000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });

  await page.goto("http://127.0.0.1:8790/reports", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(9000);

  console.log("body text length:", await page.evaluate(() => {
    const e = document.getElementById("body");
    return e ? e.textContent.length : -1;
  }));
  console.log("body first 200:", await page.evaluate(() => {
    const e = document.getElementById("body");
    return e ? e.textContent.slice(0, 200) : "(missing)";
  }));
  console.log("has #monthly:", await page.evaluate(() => !!document.getElementById("monthly")));
  console.log("has #split:", await page.evaluate(() => !!document.getElementById("split")));
  console.log("months rendered:", await page.evaluate(() => document.querySelectorAll("#monthly tbody tr").length));
  console.log("split kpis:", await page.evaluate(() => document.querySelectorAll("#split .kpi").length));
  console.log("status:", await page.evaluate(() => {
    const e = document.getElementById("status");
    return e ? e.textContent : "(none)";
  }));
  console.log("alerts:", await page.evaluate(() => {
    const e = document.getElementById("alerts");
    return e ? e.textContent.slice(0, 200) : "(none)";
  }));
  console.log("errors:", errors.slice(0, 4));
  console.log("typeof monthlyTable:", await page.evaluate(() => typeof monthlyTable));
  console.log("typeof dayTable:", await page.evaluate(() => typeof dayTable));
  console.log("typeof splitHtml:", await page.evaluate(() => typeof splitHtml));

  await browser.close();
})().catch((e) => { console.error("ERR", e.message); process.exit(2); });
