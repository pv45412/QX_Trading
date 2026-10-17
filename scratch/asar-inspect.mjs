import fs from "node:fs";
import path from "node:path";

const ASAR =
  "C:\\Users\\preet\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\app.asar";

const buf = fs.readFileSync(ASAR);
const headerPickleLen = buf.readUInt32LE(4);
const jsonLen = buf.readUInt32LE(8);
const header = JSON.parse(buf.toString("utf8", 12, 12 + jsonLen));
const headerSize = 8 + headerPickleLen;

function walk(node, base, out) {
  for (const [name, entry] of Object.entries(node.files || {})) {
    const p = path.posix.join(base, name);
    if (entry.files) walk(entry, p, out);
    else out.push({ path: p, offset: entry.offset, size: entry.size });
  }
}

const files = [];
walk(header, "", files);
console.log("TOTAL FILES:", files.length);
console.log("HEADER SIZE:", headerSize);

const want = [
  "dsh-skill",
  "dsh-tool-skill",
  "dsh-skill-filesystem",
  "dsh-tools",
  "dsh-client",
  "dsh-web-app",
  "dsh-web",
  "dsh-plugin-manager",
  "dsh-commands",
  "dsh-command-runtime",
  "dsh-hmr",
  "dsh-base",
  "dsh-client-ui",
  "dsh-notification",
  "dsh-toast",
];

const matched = files.filter((f) => want.some((w) => f.path.includes(w)));
console.log("\n=== MATCHED ===");
for (const m of matched) console.log(m.path);