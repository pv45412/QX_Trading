// Regression: the Settings page must offer a way to COMPLETE Schwab authorization.
//
// History: the page rendered an authorization URL and told the user to "paste the
// redirect URL into Reports -> or the Trade page OAuth box". Neither box existed and
// there was no POST route, so the flow dead-ended and the token could never be
// refreshed from the app.
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8790";
let pass = 0;
let fail = 0;
const check = (label, ok, extra = "") => {
  if (ok) {
    pass += 1;
    console.log(`  PASS  ${label}${extra ? " :: " + extra : ""}`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${label}${extra ? " :: " + extra : ""}`);
  }
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message)));

  console.log("== settings page: authorization entry point ==");
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => /Client ID/.test(document.querySelector("#creds")?.textContent || ""),
    { timeout: 120000 },
  );
  await page.waitForTimeout(1500);

  const state = await page.evaluate(() => {
    const tok = document.querySelector("#tok");
    const box = document.getElementById("authcb");
    const buttons = [...document.querySelectorAll("#tok button")].map((b) => b.textContent.trim());
    return {
      tokText: tok ? tok.textContent : "",
      hasBox: !!box,
      isTextarea: box ? box.tagName : null,
      buttons,
      oldHint: document.body.textContent.includes("Trade page OAuth box"),
      hasAuthUrlEl: !!document.getElementById("authurl"),
    };
  });

  check("authorization URL is rendered", state.hasAuthUrlEl, "id=authurl");
  check("a paste field exists for the callback", state.hasBox, state.isTextarea || "missing");
  check("there is a submit control", state.buttons.some((b) => /Complete authorization/i.test(b)),
    state.buttons.join(" | "));
  check("there is an open control", state.buttons.some((b) => /Open/i.test(b)));
  check("stale 'Trade page OAuth box' hint removed", !state.oldHint);

  console.log("\n== the submit actually reaches a route ==");
  // Drive the real handler with a deliberately bogus code; Schwab must reject it and
  // the page must surface that rather than silently doing nothing.
  await page.fill("#authcb", "https://127.0.0.1/?code=NOTAREALCODE&session=x");
  await page.click("text=Complete authorization");
  await page.waitForFunction(
    () => {
      const m = document.getElementById("authmsg");
      return m && /err|reject|fail|error/i.test(m.textContent) && !/Exchanging/i.test(m.textContent);
    },
    { timeout: 60000 },
  ).catch(() => {});
  const msg = await page.$eval("#authmsg", (e) => e.textContent).catch(() => "");
  check("rejected code is reported to the user", /reject|err|fail/i.test(msg), msg.slice(0, 120));

  console.log("\n== endpoint contract ==");
  const empty = await page.evaluate(async () => {
    const r = await fetch("/api/settings/schwab/authorize", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    return { status: r.status, body: await r.text() };
  });
  check("empty body -> 400 with a usable message", empty.status === 400 && /paste/i.test(empty.body),
    `HTTP ${empty.status}`);

  const bogus = await page.evaluate(async () => {
    const r = await fetch("/api/settings/schwab/authorize", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ callback: "https://127.0.0.1/?code=NOTAREALCODE" }),
    });
    return { status: r.status, body: await r.text() };
  });
  check("bogus code -> 400 and Schwab's reason is surfaced",
    bogus.status === 400 && /one-time use|rejected/i.test(bogus.body), `HTTP ${bogus.status}`);

  console.log("\n== secrets discipline ==");
  const html = await page.content();
  const authResponses = [empty.body, bogus.body, msg].join(" ");
  check("no access_token leaked in responses", !/"access_token"\s*:\s*"/.test(authResponses));
  check("no refresh_token leaked in responses", !/"refresh_token"\s*:\s*"/.test(authResponses));
  check("no token value in the DOM", !/"access_token"\s*:\s*"/.test(html));
  check("no uncaught page errors", errors.length === 0, errors.slice(0, 2).join(" | ") || "clean");

  const fs = require("fs");
  fs.mkdirSync("C:/Project/2026/data/reports/qx_ui", { recursive: true });
  await page.screenshot({
    path: "C:/Project/2026/data/reports/qx_ui/settings-schwab-authorize.png",
    fullPage: true,
  });
  console.log("  screenshot: data/reports/qx_ui/settings-schwab-authorize.png");

  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => {
  console.error("SUITE ERROR:", e.message);
  process.exit(2);
});
