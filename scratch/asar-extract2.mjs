import fs from "node:fs";
import path from "node:path";

const ASAR = "C:\\Users\\preet\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\app.asar";
const OUT = "C:\\Project\\2026\\scratch\\asar-extract";
const buf = fs.readFileSync(ASAR);
const jsonLen = buf.readUInt32LE(12);
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
  "dsh/node_modules/@deepseek-ai/cordis-plugin-loader/",
  "dsh/node_modules/@deepseek-ai/cordis-plugin-include/",
  "dsh/node_modules/@deepseek-ai/dsh-host-webserver/",
  "dsh/node_modules/@deepseek-ai/dsh-cordis-host-runner/",
  "dsh/node_modules/@deepseek-ai/dsh-client-modules/",
  "dsh/node_modules/@deepseek-ai/dsh-api-remotes/",
  "dsh/node_modules/@deepseek-ai/cordis/",
  "dsh/node_modules/@deepseek-ai/cosmokit/",
  "dsh/node_modules/@deepseek-ai/dsh-tool-present/",
  "dsh/node_modules/@deepseek-ai/dsh-inspect/",
  "dsh/node_modules/@deepseek-ai/dsh-client-connection/",
];
const TEXT_EXT = new Set([".js", ".cjs", ".mjs", ".ts", ".tsx", ".d.ts", ".json", ".md", ".yml", ".yaml"]);
let n = 0;
for (const f of files) {
  if (!PREFIXES.some((p) => f.path.startsWith(p))) continue;
  if (!TEXT_EXT.has(path.posix.extname(f.path))) continue;
  const abs = headerSize + f.offset;
  const dest = path.join(OUT, f.path);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, buf.subarray(abs, abs + f.size));
  n++;
}
console.log("EXTRACTED", n, "additional files");