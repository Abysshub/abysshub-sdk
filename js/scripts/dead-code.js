// Runs knip on the package in the working directory (js/ or n8n/) and compares its
// findings with the package's dead-code.json, the findings recorded when the check
// began. A new finding fails, and so does a recorded one that is gone: the record only
// shrinks. Exits 1 on either.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const report = JSON.parse(
  execFileSync("npx", ["knip", "--reporter", "json", "--no-exit-code", "--no-progress"], { encoding: "utf8" }),
);
const found = new Set();
for (const { file, ...types } of report.issues) {
  for (const [type, items] of Object.entries(types)) {
    // duplicates and cycles are each a list of the names involved
    for (const item of items) {
      const name = Array.isArray(item) ? item.map((each) => each.name).join(", ") : item.name;
      found.add(`${file} ${type} ${name}`);
    }
  }
}
const recorded = new Set(JSON.parse(readFileSync("dead-code.json", "utf8")));
const fresh = [...found].filter((finding) => !recorded.has(finding));
const gone = [...recorded].filter((finding) => !found.has(finding));
for (const finding of fresh) console.log(`✗ new dead code: ${finding}`);
for (const finding of gone) console.log(`✗ gone, so remove it from dead-code.json: ${finding}`);
if (fresh.length === 0 && gone.length === 0) console.log(`✓ knip: ${found.size} recorded findings, none new`);
process.exitCode = fresh.length + gone.length > 0 ? 1 : 0;
