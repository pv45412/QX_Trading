// Scratch: why does the carried ticket fail local validation?
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));

  await page.goto("http://127.0.0.1:8790/scanner", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("#results tbody tr").length > 0, { timeout: 240000 });
  await page.click("#results tbody tr");
  await page.waitForFunction(() => /Score breakdown/.test(document.querySelector("#sel").textContent), { timeout: 120000 });
  await page.click("text=Open Trade Workspace");
  await page.waitForURL(/\/trade/, { timeout: 60000 });
  await page.waitForFunction(() => /Equity/.test(document.querySelector("#acctkpi").textContent), { timeout: 180000 });

  console.log("setup in storage:", await page.evaluate(() => localStorage.getItem("qx.selectedSetup")));
  console.log("ticket fields:", await page.evaluate(() => ({
    sym: document.querySelector("#t_sym").value,
    side: document.querySelector("#t_side").value,
    qty: document.querySelector("#t_qty").value,
    type: document.querySelector("#t_type").value,
    limit: document.querySelector("#t_limit").value,
    dur: document.querySelector("#t_dur").value,
    acct: document.querySelector("#acct").value,
  })));

  const direct = await page.evaluate(async () => {
    const setup = JSON.parse(localStorage.getItem("qx.selectedSetup") || "null");
    const ticket = {
      account: document.querySelector("#acct").value,
      symbol: document.querySelector("#t_sym").value.trim().toUpperCase(),
      side: document.querySelector("#t_side").value,
      quantity: Number(document.querySelector("#t_qty").value || 0),
      order_type: document.querySelector("#t_type").value,
      limit_price: document.querySelector("#t_limit").value === "" ? null : Number(document.querySelector("#t_limit").value),
      duration: document.querySelector("#t_dur").value,
      setup: setup,
    };
    const r = await fetch("/api/trade/validate", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(ticket),
    });
    return { status: r.status, body: await r.json() };
  });
  console.log("verdict:", direct.body.verdict);
  console.log("failed:", JSON.stringify(direct.body.failed));
  console.log("checks:");
  for (const c of direct.body.checks) console.log("   ", c.passed ? "PASS" : "FAIL", c.name, "::", c.detail);

  await browser.close();
})().catch((e) => { console.error("ERR", e.message); process.exit(2); });
