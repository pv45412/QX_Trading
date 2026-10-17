// @qx/schwab-plugin — DSH host plugin: Schwab data + SMC rules engine + alerts.
//
// Dependency-free on purpose: it is loaded by the DSH Loader inside the host
// process, so it imports nothing outside Node built-ins. Every capability it
// exposes (skills, tools, a web dashboard, a rule poller) is registered through
// the Cordis `ctx` it receives.
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const WORKER = fileURLToPath(new URL("../python/qx_schwab_worker.py", import.meta.url));

const DEFAULT_CONFIG = {
  pythonPath: "C:/Project/2026/.venv/Scripts/python.exe",
  workspaceRoot: "C:/Project/2026",
  watchlist: ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "AMZN", "GOOGL"],
  pollEnabled: false,
  pollIntervalSeconds: 180,
  scanTimeoutMs: 90000,
};

export const name = "qx-schwab";

// --------------------------------------------------------------------------- //
// State
// --------------------------------------------------------------------------- //

function createState() {
  return {
    status: null,
    lastScan: null,
    alerts: [], // { id, symbol, signal, side, score, text, at }
    confirmed: [], // staged (paper) artifacts
    log: [],
    lastError: null,
  };
}

// --------------------------------------------------------------------------- //
// Python worker bridge
// --------------------------------------------------------------------------- //

function runWorker(cfg, cmd, payload) {
  return new Promise((resolve) => {
    const child = spawn(cfg.pythonPath, [WORKER, cmd], {
      cwd: cfg.workspaceRoot,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let out = "";
    let err = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve({ ok: false, error: `worker timed out (${cfg.scanTimeoutMs}ms)`, stderr: err });
    }, cfg.scanTimeoutMs);
    child.stdout.on("data", (d) => { out += d; });
    child.stderr.on("data", (d) => { err += d; });
    child.on("error", (e) => {
      clearTimeout(timer);
      resolve({ ok: false, error: `python spawn failed: ${String(e && e.message ? e.message : e)}`, stderr: err });
    });
    child.on("close", () => {
      clearTimeout(timer);
      let parsed;
      try { parsed = JSON.parse(out.trim()); }
      catch {
        parsed = { ok: false, error: "worker returned non-JSON", raw: String(out).slice(0, 2000), stderr: String(err).slice(0, 2000) };
      }
      resolve(parsed);
    });
    if (payload !== undefined) child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

// --------------------------------------------------------------------------- //
// Alerts derivation
// --------------------------------------------------------------------------- //

function ingestScan(state, scan) {
  if (!scan || !Array.isArray(scan.results)) return;
  const seen = new Set(state.alerts.map((a) => a.id));
  for (const r of scan.results) {
    if (r.error) continue;
    for (const text of r.alerts || []) {
      const id = `${r.symbol}::${text}`;
      const existing = state.alerts.find((a) => a.id === id);
      if (existing) { existing.symbol = r.symbol; existing.score = r.score; existing.signal = r.signal; existing.side = r.side; existing.at = new Date().toISOString(); continue; }
      state.alerts.push({ id, symbol: r.symbol, signal: r.signal, side: r.side, score: r.score, text, at: new Date().toISOString() });
    }
  }
  // drop alerts whose symbol no longer has a matching line
  const live = scan.results.flatMap((r) => (r.alerts || []).map((t) => `${r.symbol}::${t}`));
  state.alerts = state.alerts.filter((a) => live.includes(a.id));
  state.alerts.sort((a, b) => Number(b.score ?? 0) - Number(a.score ?? 0));
}

function persistConfirmed(state, cfg) {
  const dir = path.join(cfg.workspaceRoot, "data", "qx_alerts");
  try {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "staged_orders.json"), JSON.stringify(state.confirmed, null, 2));
  } catch (e) { state.log.push(`persist failed: ${e}`); }
}

// --------------------------------------------------------------------------- //
// Skills (embody the workspace SMC rules-engine studies + spec)
// --------------------------------------------------------------------------- //

const RESOURCE_BASE = {
  kind: "directory",
  path: "C:/Project/2026/.agents/skills/smc-rules-engine/resources",
};

const SKILLS = [
  {
    name: "schwab-rules-engine",
    description: "Run the QX SMC rules engine over real Schwab market data to score symbols (0-100) and surface LONG/SHORT/WAIT signals and per-factor alerts.",
    whenToUse: "When the user asks to scan, pick, or rank stocks/ETFs to trade, or asks what the rules engine says about a symbol.",
    source: "qx-schwab-plugin",
    resourceBase: RESOURCE_BASE,
    content: [
      "# Schwab Rules Engine",
      "",
      "You drive the QX rules engine through the `qx_schwab_*` tools. This mirrors the workspace specification",
      "`.agents/skills/smc-rules-engine/resources/qx_rules_engine_spec.md` and the 12 ThinkScript studies in that directory.",
      "",
      "## Scoring model",
      "QX Score = 0.25*SMC + 0.20*Phases + 0.20*CVD_Absorption + 0.15*VScore + 0.10*RS_Rank + 0.10*OptionsFlow.",
      "- score >= 70  -> LONG / BUY CALL",
      "- score <= 30  -> SHORT / BUY PUT",
      "- otherwise    -> WAIT",
      "",
      "## Workflow",
      "1. `qx_schwab_status` — confirm Schwab auth/data source state first.",
      "2. `qx_schwab_scan` — fetch bars/quotes and score one or more symbols.",
      "3. `qx_schwab_alerts` — read the currently active rule alerts.",
      "4. When a rule (or the aggregate signal) is met, surface it to the user in plain language as an on-screen alert with symbol, side, score, and the factors that fired.",
      "",
      "## Rules of engagement",
      "- Prefer live Schwab data; the worker transparently falls back to cached bars when Schwab is unavailable and reports the source.",
      "- Never invent prices or scores — always read them from tool results.",
      "- A WAIT signal is not a trade; do not present it as one.",
      "- Studies live in the resources directory (`*.tos` + the spec). Read them when the user asks for the exact study logic.",
    ].join("\n"),
  },
  {
    name: "schwab-trade-desk",
    description: "The confirm-to-execute workflow: take a rules-engine signal, get explicit human confirmation, and stage the order (paper/fail-closed — never a live Schwab submission).",
    whenToUse: "When the user wants to act on an alert, confirm a trade, or stage an order from a rules-engine signal.",
    source: "qx-schwab-plugin",
    resourceBase: RESOURCE_BASE,
    content: [
      "# Schwab Trade Desk (fail-closed)",
      "",
      "Use `qx_schwab_confirm_trade` to stage a trade ONLY after the user has explicitly confirmed it.",
      "",
      "## Hard safety rule (non-negotiable)",
      "This workspace PROHIBITS live broker writes / execution (see PROJECT_STATE.md: milestones EX0-EX3 are BACKLOG).",
      "`qx_schwab_confirm_trade` therefore **stages a paper/simulated order** and never submits to Schwab.",
      "Always say this explicitly to the user: the order is STAGED for review, not executed.",
      "",
      "## Workflow",
      "1. Identify a symbol + side from a `qx_schwab_scan` result (score threshold met).",
      "2. Quote the symbol, side, score, and the factors that fired.",
      "3. Ask the user to confirm; require an explicit yes before calling the tool.",
      "4. Call `qx_schwab_confirm_trade` with `confirm: true` and a short reason; the tool records a staged order.",
      "5. Report the staged order id and remind the user execution is gated behind the EX3 live-trading human gate.",
    ].join("\n"),
  },
  {
    name: "schwab-alert-monitor",
    description: "Monitor the rules engine for new alerts and present them on screen; trigger rescans and watch for WAIT-to-signal transitions.",
    whenToUse: "When the user wants ongoing monitoring, alerting, or to be notified the moment a rule condition is met.",
    source: "qx-schwab-plugin",
    resourceBase: RESOURCE_BASE,
    content: [
      "# Schwab Alert Monitor",
      "",
      "The plugin optionally polls a watchlist and keeps an in-memory alert ledger, also served live at",
      "`http://127.0.0.1:19387/qx/schwab` (open it for a visual desk).",
      "",
      "To monitor: `qx_schwab_scan` a watchlist, then `qx_schwab_alerts` to read the ledger.",
      "Treat every non-WAIT aggregate signal and every factor alert as a notification to surface to the user.",
      "Deduplicate on the alert id (symbol::text); signal transitions are the interesting events.",
    ].join("\n"),
  },
];

// --------------------------------------------------------------------------- //
// Plugin entry
// --------------------------------------------------------------------------- //

export function apply(ctx, config = {}) {
  const cfg = { ...DEFAULT_CONFIG, ...(config || {}) };
  const state = createState();
  const disposers = [];

  // ---- skills ----
  if (ctx.skills) {
    for (const skill of SKILLS) {
      try {
        disposers.push(ctx.skills.register(skill));
      } catch (e) {
        ctx.logger?.warn?.(`qx-schwab: skill register failed for ${skill.name}: ${e}`);
      }
    }
  }

  // ---- tools ----
  if (ctx.tools) {
    disposers.push(ctx.tools.register(statusTool(cfg, state)));
    disposers.push(ctx.tools.register(authUrlTool(cfg, state)));
    disposers.push(ctx.tools.register(authorizeTool(cfg, state)));
    disposers.push(ctx.tools.register(scanTool(cfg, state)));
    disposers.push(ctx.tools.register(alertsTool(state)));
    disposers.push(ctx.tools.register(confirmTool(cfg, state)));
  }

  // ---- web dashboard ----
  if (ctx.webServer) {
    disposers.push(ctx.webServer.register({ kind: "prefix", path: "/qx/schwab", handler: routeHandler(cfg, state) }));
    ctx.logger?.info?.(`qx-schwab dashboard at /qx/schwab (${ctx.webServer.host}:${ctx.webServer.port})`);
  }

  // ---- poller ----
  let timer = null;
  async function poll() {
    const res = await runWorker(cfg, "scan", { symbols: cfg.watchlist });
    if (res && res.ok && res.scan) {
      state.lastScan = res.scan;
      ingestScan(state, res.scan);
    } else if (res && !res.ok) {
      state.lastError = res.error || "scan failed";
    }
  }
  if (cfg.pollEnabled && Number(cfg.pollIntervalSeconds) > 0) {
    timer = setInterval(poll, Number(cfg.pollIntervalSeconds) * 1000);
    poll().catch(() => {});
  }

  // initial status fetch so the dashboard has auth data immediately
  runWorker(cfg, "status", undefined).then((res) => { state.status = res && res.status ? res.status : { message: String(res && res.error) }; }).catch(() => {});

  ctx.on("dispose", () => {
    if (timer) clearInterval(timer);
    for (const d of disposers) { try { d(); } catch {} }
  });

  // expose the bridge for diagnostics
  return { status: () => state, runWorker: (cmd, payload) => runWorker(cfg, cmd, payload) };
}

export default { name, apply };

// --------------------------------------------------------------------------- //
// Tools
// --------------------------------------------------------------------------- //

function statusTool(cfg, state) {
  return {
    name: "qx_schwab_status",
    description: "Report Schwab authentication/health and the current data-source state for the QX rules engine.",
    parameters: { type: "object", additionalProperties: false, properties: {} },
    output: { schema: {}, render: (_a, v) => [{ type: "text", text: v.summary }] },
    async execute() {
      const res = await runWorker(cfg, "status", undefined);
      const status = res && res.status ? res.status : { message: String(res && res.error) };
      state.status = status;
      if (res && res.ok) state.lastError = null;
      return {
        ok: Boolean(res && res.ok),
        configured: Boolean(status.configured),
        has_token: Boolean(status.has_token),
        access_token_valid: Boolean(status.access_token_valid),
        refresh_token_valid: Boolean(status.refresh_token_valid),
        message: status.message,
        api_base_url: status.api_base_url,
        last_scan_symbols: state.lastScan ? state.lastScan.symbols : 0,
        summary: `Schwab: ${status.message}\nLast scan: ${state.lastScan ? `${state.lastScan.symbols} symbols (${state.lastScan.actionable} actionable), source ${state.lastScan.spxSource || "?"}` : "none yet"}`,
      };
    },
  };
}

function authUrlTool(cfg, state) {
  return {
    name: "qx_schwab_auth_url",
    description: "Return the Schwab OAuth authorization URL the user must open to (re)enable live data.",
    parameters: { type: "object", additionalProperties: false, properties: {} },
    output: { schema: {}, render: (_a, v) => [{ type: "text", text: v.url || v.error }] },
    async execute() {
      const res = await runWorker(cfg, "auth_url", undefined);
      return res && res.ok ? { url: res.url } : { error: res && res.error };
    },
  };
}

function authorizeTool(cfg, state) {
  return {
    name: "qx_schwab_authorize",
    description: "Exchange a Schwab OAuth authorization code (or callback URL) to complete re-authorization and re-enable live data.",
    parameters: {
      type: "object", additionalProperties: false,
      properties: { callback: { type: "string", description: "The full redirect/callback URL or bare code from Schwab after login." } },
      required: ["callback"],
    },
    output: { schema: {}, render: (_a, v) => [{ type: "text", text: v.message || v.error }] },
    async execute(args) {
      const res = await runWorker(cfg, "authorize", String(args.callback || ""));
      if (res && res.ok) { state.status = { has_token: true, access_token_valid: Boolean(res.access_token_valid), message: res.message }; state.lastError = null; }
      return res && res.ok ? { ok: true, has_token: Boolean(res.has_token), message: res.message }
        : { ok: false, error: res && res.error };
    },
  };
}

function scanTool(cfg, state) {
  return {
    name: "qx_schwab_scan",
    description: "Fetch Schwab (or cached) bars and quotes and run the SMC rules engine, returning a 0-100 score, LONG/SHORT/WAIT signal, and per-factor alerts for each symbol.",
    parameters: {
      type: "object", additionalProperties: false,
      properties: {
        symbols: { type: "array", items: { type: "string" }, description: "Tickers to scan, e.g. [\"SPY\",\"AAPL\"]. Defaults to the plugin watchlist." },
      },
    },
    output: { schema: {}, render: (_a, v) => [{ type: "text", text: v.summary }] },
    async execute(args) {
      const symbols = (args.symbols && args.symbols.length ? args.symbols : cfg.watchlist).map((s) => String(s).toUpperCase());
      const res = await runWorker(cfg, "scan", { symbols });
      if (!res || !res.ok || !res.scan) return { ok: false, error: res && res.error, summary: `scan failed: ${res && res.error}` };
      state.lastScan = res.scan;
      ingestScan(state, res.scan);
      state.lastError = null;
      const rows = res.scan.results || [];
      const actionable = rows.filter((r) => r.side);
      const summary = [
        `QX scan: ${res.scan.symbols} symbols, ${actionable.length} actionable (source ${res.scan.spxSource}).`,
        ...actionable.map((r) => `${r.signal} ${r.symbol} score=${r.score} (${Object.entries(r.factors).map(([k, v]) => `${k} ${v}`).join(", ")})`),
        rows.filter((r) => r.side).length ? "" : "No non-WAIT signals in this scan.",
      ].filter(Boolean).join("\n");
      return {
        ok: true,
        generatedAt: res.scan.generatedAt,
        spxSource: res.scan.spxSource,
        actionable: actionable.length,
        rows,
        alerts: state.alerts,
        summary,
      };
    },
  };
}

function alertsTool(state) {
  return {
    name: "qx_schwab_alerts",
    description: "Read the active rules-engine alert ledger (rule conditions and signals currently met).",
    parameters: { type: "object", additionalProperties: false, properties: {} },
    output: { schema: {}, render: (_a, v) => [{ type: "text", text: v.summary }] },
    async execute() {
      const summary = state.alerts.length
        ? state.alerts.map((a) => `[${a.at}] ${a.signal} ${a.symbol} score=${a.score ?? "-"} — ${a.text}`).join("\n")
        : "No active alerts. Run qx_schwab_scan first.";
      return { count: state.alerts.length, alerts: state.alerts, summary };
    },
  };
}

function confirmTool(cfg, state) {
  return {
    name: "qx_schwab_confirm_trade",
    description: "Stage (paper/simulated) an order for a rules-engine signal after explicit human confirmation. FAIL-CLOSED: never submits a live Schwab order.",
    parameters: {
      type: "object", additionalProperties: false,
      properties: {
        symbol: { type: "string", description: "Ticker symbol." },
        side: { type: "string", enum: ["LONG", "SHORT"], description: "Direction from the scan signal." },
        quantity: { type: "number", description: "Optional share/contract quantity for the staged order." },
        reason: { type: "string", description: "Short reason (score + factors)." },
        confirm: { type: "boolean", description: "Explicit human confirmation to stage this trade." },
      },
      required: ["symbol", "side", "confirm"],
    },
    output: { schema: {}, render: (_a, v) => [{ type: "text", text: v.summary }] },
    async execute(args) {
      if (args.confirm !== true) {
        return { ok: false, staged: false, summary: "Not staged: `confirm` must be explicitly true (human confirmation required)." };
      }
      const artifact = {
        id: `QX-${Date.now().toString(36).toUpperCase()}`,
        symbol: String(args.symbol).toUpperCase(),
        side: args.side,
        quantity: Number(args.quantity || 0),
        reason: String(args.reason || ""),
        status: "STAGED (paper — live execution gated behind EX3 human approval)",
        at: new Date().toISOString(),
      };
      state.confirmed.push(artifact);
      persistConfirmed(state, cfg);
      return {
        ok: true,
        staged: true,
        artifact,
        summary: `STAGED (paper) ${artifact.id}: ${artifact.side} ${artifact.symbol} qty=${artifact.quantity} — ${artifact.reason}\nREMINDER: no live Schwab order was placed; execution is fail-closed per PROJECT_STATE.md.`,
      };
    },
  };
}

// --------------------------------------------------------------------------- //
// Web dashboard
// --------------------------------------------------------------------------- //

function routeHandler(cfg, state) {
  return async (req, res) => {
    const url = new URL(req.url || "/", "http://x");
    const p = url.pathname;
    try {
      if (p === "/qx/schwab" || p === "/qx/schwab/") return sendHtml(res, DASHBOARD);
      if (p === "/qx/schwab/api/state") return sendJson(res, apiState(state, cfg));
      if (p === "/qx/schwab/api/scan" && req.method === "POST") {
        const body = await readBody(req);
        const res2 = await runWorker(cfg, "scan", { symbols: (body.symbols || cfg.watchlist).map((s) => String(s).toUpperCase()) });
        if (res2 && res2.ok && res2.scan) { state.lastScan = res2.scan; ingestScan(state, res2.scan); state.lastError = null; }
        return sendJson(res, apiState(state, cfg));
      }
      if (p === "/qx/schwab/api/confirm" && req.method === "POST") {
        const body = await readBody(req);
        const artifact = {
          id: `QX-${Date.now().toString(36).toUpperCase()}`,
          symbol: String(body.symbol || "").toUpperCase(),
          side: body.side,
          quantity: Number(body.quantity || 0),
          reason: String(body.reason || ""),
          status: "STAGED (paper — live execution gated behind EX3 human approval)",
          at: new Date().toISOString(),
        };
        state.confirmed.push(artifact);
        persistConfirmed(state, cfg);
        return sendJson(res, apiState(state, cfg));
      }
      if (p === "/qx/schwab/api/auth-url") {
        const res2 = await runWorker(cfg, "auth_url", undefined);
        return sendJson(res, res2 && res2.ok ? { url: res2.url } : { error: res2 && res2.error });
      }
      if (p === "/qx/schwab/api/auth" && req.method === "POST") {
        const body = await readBody(req);
        const res2 = await runWorker(cfg, "authorize", String(body.callback || ""));
        if (res2 && res2.ok) { state.status = { has_token: true, access_token_valid: Boolean(res2.access_token_valid), message: res2.message }; state.lastError = null; }
        else { state.lastError = (res2 && res2.error) || "authorize failed"; }
        return sendJson(res, apiState(state, cfg));
      }
      res.writeHead(404); res.end("not found");
    } catch (e) {
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) }));
    }
  };
}

function apiState(state, cfg) {
  return {
    status: state.status,
    lastScan: state.lastScan,
    alerts: state.alerts,
    confirmed: state.confirmed,
    lastError: state.lastError,
    watchlist: cfg.watchlist,
    poll: { enabled: Boolean(cfg.pollEnabled), intervalSeconds: cfg.pollIntervalSeconds },
  };
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => { data += c; if (data.length > 2_000_000) { resolve({}); req.destroy(); } });
    req.on("end", () => { try { resolve(JSON.parse(data || "{}")); } catch { resolve({}); } });
    req.on("error", () => resolve({}));
  });
}
function sendJson(res, value) {
  res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(JSON.stringify(value));
}
function sendHtml(res, html) {
  res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  res.end(html);
}

const DASHBOARD = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>QX Schwab Trading Desk</title>
<style>
:root{--bg:#0b1020;--panel:#131a30;--line:#26314f;--fg:#e7ecf7;--mut:#8a93ad;--up:#2ecc71;--dn:#e74c3c;--acc:#4c8dff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,Segoe UI,sans-serif;padding:20px}
h1{font-size:20px;margin:0 0 4px}h1 small{color:var(--mut);font-weight:400}
.grid{display:grid;grid-template-columns:1fr 300px;gap:16px;max-width:1180px;margin:0 auto}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin:0 0 10px}
.bar{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.kv{color:var(--mut)}.kv b{color:var(--fg);font-weight:600;margin-left:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-weight:700;font-size:12px}
.LONG,.BUY{background:rgba(46,204,113,.15);color:var(--up)}
.SHORT,.SELL{background:rgba(231,76,60,.15);color:var(--dn)}
.WAIT{background:rgba(255,255,255,.08);color:var(--mut)}
button{background:var(--acc);border:0;color:#fff;padding:8px 14px;border-radius:8px;cursor:pointer;font-weight:600}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg)}
button:hover{filter:brightness(1.1)}
input{width:100%;background:#0d1428;border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:8px;margin:6px 0;font:inherit}
.staged{background:rgba(76,141,255,.07);border-left:3px solid var(--acc)}
.mut{color:var(--mut);font-size:12px}
a{color:var(--acc)}
code{background:#0d1428;padding:1px 6px;border-radius:6px}
</style></head><body>
<div class="grid"><div>
  <h1>QX Schwab Trading Desk <small>&ldquo;rules met &rarr; confirm to execute&rdquo; (paper, fail-closed)</small></h1>
  <div class="card"><h2>Status</h2><div id="status" class="bar"></div></div>
  <div class="card"><h2>Live Alerts</h2><div id="alerts"><table><tr><th>Time</th><th>Symbol</th><th>Signal</th><th>Score</th><th>Rule</th><th></th></tr></table></div></div>
  <div class="card"><h2>Scan Results</h2><div id="results"><span class="mut">Run a scan.</span></div></div>
  <div class="card"><h2>Staged Orders (paper)</h2><div id="confirmed"><span class="mut">None yet.</span></div></div>
</div><div>
  <div class="card"><h2>Actions</h2>
    <button onclick="scan()">Scan watchlist now</button>
    <div class="mut" style="margin-top:8px">Watchlist: <span id="watchlist"></span></div>
  </div>
  <div class="card"><h2>Schwab OAuth</h2>
    <div class="mut">Live Schwab needs a fresh authorization. Open the URL below, log in, copy the redirect URL, and paste it back.</div>
    <button class="ghost" onclick="authUrl()">Copy / open authorization URL</button>
    <input id="callback" placeholder="Paste callback URL or code"/>
    <button onclick="authorize()">Complete re-authorization</button>
  </div>
</div></div>
<script>
const P=document.querySelector('#status'),A=document.querySelector('#alerts'),R=document.querySelector('#results'),C=document.querySelector('#confirmed'),W=document.querySelector('#watchlist');
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function j(m,u,b){const r=await fetch(u,{method:m,headers:{'content-type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json()}
function pill(s){return '<span class="pill '+esc(s)+'">'+esc(s)+'</span>'}
function render(d){
  const st=d.status||{};
  P.innerHTML='<div class="kv">Auth<b>'+esc(st.message||'unknown')+'</b></div>'+
     '<div class="kv">Token<b>'+(st.has_token?'present':'none')+'</b></div>'+
     '<div class="kv">Access valid<b>'+(st.access_token_valid?'yes':'no')+'</b></div>'+
     '<div class="kv">Last scan<b>'+(d.lastScan?esc(d.lastScan.symbols)+' syms / '+d.lastScan.actionable+' actionable':'—')+'</b></div>'+
     '<div class="kv">Data source<b>'+esc(d.lastScan?d.lastScan.spxSource:'—')+'</b></div>'+
     (d.lastError?'<div class="kv">Error<b style="color:#e74c3c">'+esc(d.lastError)+'</b></div>':'');
  W.textContent=(d.watchlist||[]).join(', ');
  const als=d.alerts||[];
  A.innerHTML=als.length?
    '<table><tr><th>Time</th><th>Symbol</th><th>Signal</th><th>Score</th><th>Rule</th><th></th></tr>'+als.map(a=>
      '<tr><td class="mut">'+esc((a.at||'').slice(11,19))+'</td><td><b>'+esc(a.symbol)+'</b></td><td>'+pill(a.signal||a.side||'')+'</td><td>'+(a.score==null?'—':a.score)+'</td><td>'+esc(a.text)+'</td>'+
      '<td><button onclick="confirm(\''+esc(a.symbol)+'\',\''+esc(a.side)+'\','+(a.score||0)+')">Confirm</button></td></tr>').join('')+'</table>'
    :'<span class="mut">No active alerts. Run a scan.</span>';
  const rs=(d.lastScan&&d.lastScan.results)||[];
  R.innerHTML=rs.length?
    '<table><tr><th>Symbol</th><th>Signal</th><th>Score</th><th>Factors</th><th>Last</th></tr>'+rs.map(r=>
      '<tr><td><b>'+esc(r.symbol)+'</b></td><td>'+pill(r.signal)+'</td><td>'+(r.score==null?'—':r.score)+'</td><td class="mut">'+(r.factors?Object.entries(r.factors).map(([k,v])=>k+' '+v).join(' · '):'')+'</td><td>'+(r.last==null?'—':r.last)+'</td></tr>').join('')+'</table>'
    :'<span class="mut">Run a scan.</span>';
  const cf=d.confirmed||[];
  C.innerHTML=cf.length?cf.map(o=>'<div class="staged" style="padding:8px 10px;margin:6px 0;border-radius:8px"><b>'+esc(o.id)+'</b> · '+pill(o.side)+' <b>'+esc(o.symbol)+'</b> qty='+esc(o.quantity)+'<div class="mut">'+esc(o.status)+'</div><div class="mut">'+esc(o.reason)+'</div></div>').join(''):'<span class="mut">None yet.</span>';
}
async function refresh(){try{render(await j('GET','/qx/schwab/api/state'))}catch(e){}}
async function scan(){await j('POST','/qx/schwab/api/scan');refresh()}
async function confirm(sym,side,score){await j('POST','/qx/schwab/api/confirm',{symbol:sym,side:side,reason:'Confirmed from dashboard (score '+score+')'});refresh()}
async function authUrl(){const r=await j('GET','/qx/schwab/api/auth-url');if(r&&r.url){window.prompt('Copy this URL and open it in a browser, log in, then paste the redirect URL back below:',r.url);try{await navigator.clipboard.writeText(r.url)}catch(e){}}else{alert('Could not get authorization URL: '+(r&&r.error||'unknown'))}}
async function authorize(){const cb=document.querySelector('#callback').value;const r=await j('POST','/qx/schwab/api/auth',{callback:cb});render(r)}
refresh();setInterval(refresh,5000);
</script></body></html>`;

export { DASHBOARD, apiState, runWorker };