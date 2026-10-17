import fs from "node:fs";

const ASAR =
  "C:\\Users\\preet\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\app.asar";
const buf = fs.readFileSync(ASAR);

console.log("size:", buf.length);
for (let i = 0; i < 32; i += 4) {
  console.log(
    `bytes[${i}..${i + 3}] = ${buf.readUInt32LE(i)}  (hex ${buf
      .subarray(i, i + 4)
      .toString("hex")})`
  );
}
console.log("ascii 0..24:", JSON.stringify(buf.toString("utf8", 0, 24)));

// find the JSON header start
const j = buf.indexOf('{"files"');
console.log("indexOf '{\"files\"':", j);
// balanced brace scan
function scan(start) {
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < buf.length && i < start + 80 * 1024 * 1024; i++) {
    const c = buf[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === 0x5c) esc = true;
      else if (c === 0x22) inStr = false;
      continue;
    }
    if (c === 0x22) inStr = true;
    else if (c === 0x7b) depth++;
    else if (c === 0x7d) {
      depth--;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}
if (j > 0) {
  const end = scan(j);
  console.log("json end index:", end, "json length:", end - j);
  console.log("head of json:", JSON.stringify(buf.toString("utf8", j, j + 60)));
  console.log("tail of json:", JSON.stringify(buf.toString("utf8", end - 40, end)));
  const json = JSON.parse(buf.toString("utf8", j, end));
  console.log("parsed OK. top-level keys:", Object.keys(json));
}