import fs from "node:fs";
import path from "node:path";

const ASAR =
  "C:\\Users\\preet\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\app.asar";
const OUT = "C:\\Project\\2026\\scratch\\asar-extract";

const buf = fs.readFileSync(ASAR);
const jsonLen = buf.readUInt32LE(12); // bytes 12..15
const json = JSON.parse(buf.toString("utf8", 16, 16 + jsonLen));
const headerSize = 8 + buf.readUInt32LE(4);

function walk(node, base, out) {
  for (const [name, entry] of Object.entries(node.files || {})) {
    const p = path.posix.join(base, name);
    if (entry.files) walk(entry, p, out);
    else out.push({ path: p, offset: Number(entry.offset), size: entry.size });
  }
}
const files = [];
walk(json, "", files);

const PREFIXES = [
  "dsh/node_modules/@deepseek-ai/dsh-skill/",
  "dsh/node_modules/@deepseek-ai/dsh-tool-skill/",
  "dsh/node_modules/@deepseek-ai/dsh-skill-filesystem/",
  "dsh/node_modules/@deepseek-ai/dsh-tools/",
  "dsh/node_modules/@deepseek-ai/dsh-commands/",
  "dsh/node_modules/@deepseek-ai/dsh-web/",
  "dsh/node_modules/@deepseek-ai/dsh-base/",
  "dsh/node_modules/@deepseek-ai/dsh-web-app/",
  "dsh/node_modules/@deepseek-ai/dsh-plugin-manager/",
  "dsh/node_modules/@deepseek-ai/dsh-hmr/",
  "dsh/node_modules/@deepseek-ai/dsh-notification/",
  "dsh/node_modules/@deepseek-ai/dsh-toast/",
  "dsh/node_modules/@deepseek-ai/dsh-client/",
  "dsh/node_modules/@deepseek-ai/dsh-client-ui-chat/",
  "dsh/node_modules/@deepseek-ai/dsh-client-common/",
  "dsh/node_modules/@deepseek-ai/dsh-scope/",
  "dsh/node_modules/@deepseek-ai/dsh-inspect/",
  "dsh/node_modules/@deepseek-ai/dsh-cordis/",
  "dsh/node_modules/@deepseek-ai/dsh-plugin/",
];

const TEXT_EXT = new Set([
  ".js", ".cjs", ".mjs", ".ts", ".tsx", ".d.ts", ".json", ".md", ".yml",
  ".yaml", ".html", ".css",
]);

let n = 0;
const selected = files.filter(
  (f) =>
    PREFIXES.some((p) => f.path.startsWith(p)) &&
    (TEXT_EXT.has(path.posix.extname(f.path)) || path.posix.basename(f.path) === "package.json")
);

// Also capture the top-level package.json for every @deepseek-ai/dsh-* package
const pkgJson = files.filter((f) =>
  /^dsh\/node_modules\/@deepseek-ai\/[^/]+\/package.json$/.test(f.path)
);
const seen = new Set(selected.map((f) => f.path));
for (const pj of pkgJson) {
  if (!seen.has(pj.path)) selected.push(pj);
}

for (const f of selected) {
  const abs = headerSize + f.offset;
  const dest = path.join(OUT, f.path);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, buf.subarray(abs, abs + f.size));
  n++;
}

console.log("EXTRACTED", n, "files to", OUT);
console.log("headerSize", headerSize, "jsonLen", jsonLen);
// List package.json files under @deepseek-ai
for (const pj of pkgJson) console.log("PKG:", pj);