// Find which element overflows horizontally on /reports at 420px.
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  page.setDefaultTimeout(600000);
  await page.goto("http://127.0.0.1:8790/reports", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(16000);

  const report = await page.evaluate(() => {
    const doc = document.documentElement;
    const total = doc.scrollWidth - doc.clientWidth;
    const offenders = [];
    const limit = doc.clientWidth;
    document.querySelectorAll("*").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > limit + 4) {
        offenders.push({
          tag: el.tagName.toLowerCase(),
          id: el.id || null,
          cls: (el.className && String(el.className).slice(0, 40)) || null,
          width: Math.round(r.width),
          right: Math.round(r.right),
          scrollW: el.scrollWidth,
          text: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40),
        });
      }
    });
    return { total, limit, offenders: offenders.slice(0, 12) };
  });

  console.log("viewport          :", report.limit);
  console.log("horizontal overflow:", report.total, "px");
  console.log("\nwidest offenders (element right edge beyond the viewport):");
  report.offenders.forEach((o) => {
    console.log(`  <${o.tag}${o.id ? "#" + o.id : ""}${o.cls ? "." + o.cls : ""}> ` +
      `w=${o.width} right=${o.right} scrollW=${o.scrollW} :: ${o.text}`);
  });
  if (!report.offenders.length) console.log("  (none found — overflow may come from a scroll container)");

  // Check the scroll containers specifically.
  const scrollers = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll(".scroll, .tablewrap, table").forEach((el) => {
      out.push({
        cls: String(el.className || el.tagName).slice(0, 30),
        clientW: el.clientWidth,
        scrollW: el.scrollWidth,
        overflows: el.scrollWidth > el.clientWidth + 4,
      });
    });
    return out.slice(0, 8);
  });
  console.log("\nscroll containers:");
  scrollers.forEach((s) => console.log(`  ${s.cls}: client=${s.clientW} scroll=${s.scrollW} overflows=${s.overflows}`));

  await browser.close();
})().catch((e) => { console.error("ERR:", e.message); process.exit(2); });
