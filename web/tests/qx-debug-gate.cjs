// Scratch: inspect the confirmation gate markup/state.
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  await page.goto("http://127.0.0.1:8790/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("#results tbody tr").length > 0, { timeout: 240000 });
  await page.click("#results tbody tr");
  await page.waitForFunction(() => /Score breakdown/.test(document.querySelector("#sel").textContent), { timeout: 120000 });
  await page.click("text=Open Trade Workspace");
  await page.waitForURL(/\/trade/, { timeout: 60000 });
  await page.waitForFunction(() => /Equity/.test(document.querySelector("#acctkpi").textContent), { timeout: 180000 });

  await page.fill("#t_qty", "3");
  await page.click("text=Review order");
  await page.waitForFunction(() => /Deterministic checks/.test(document.querySelector("#review").textContent),
    { timeout: 180000 });

  console.log("verdict:", await page.$eval("#verdictbadge", (e) => e.textContent.trim()));
  console.log("markup of the confirm row:",
    await page.$eval("#review", (e) => {
      const m = e.innerHTML.match(/<div class="row" style="margin-top:11px">[\s\S]*?<\/div>/);
      return m ? m[0] : "(row not found)";
    }));
  console.log("okchk present:", await page.evaluate(() => !!document.getElementById("okchk")));
  console.log("subbtn disabled:", await page.evaluate(() => {
    const b = document.getElementById("subbtn");
    return b ? b.disabled : "(missing)";
  }));
  console.log("okchk disabled:", await page.evaluate(() => {
    const c = document.getElementById("okchk");
    return c ? { disabled: c.disabled, checked: c.checked, outer: c.outerHTML } : "(missing)";
  }));

  // The declared handler must exist.
  console.log("submitOrder type:", await page.evaluate(() => typeof submitOrder));

  await browser.close();
})().catch((e) => { console.error("ERR", e.message); process.exit(2); });
