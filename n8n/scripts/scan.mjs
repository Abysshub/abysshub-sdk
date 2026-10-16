// The local equivalent of `npx @n8n/scan-community-package n8n-nodes-abysshub`, which
// scans only a published package: the same ESLint rules, run on the sources (as the
// scanner runs them on the attested source checkout) and on the built package.json and
// dist/ (as it runs them on the tarball). Exits 1 on any error.
import { SOURCE_FILE_PATTERNS, analyzePackage } from "@n8n/scan-community-package/scanner/scanner.mjs";

const root = new URL("..", import.meta.url).pathname;
const legs = [
  ["source", SOURCE_FILE_PATTERNS],
  ["package", ["dist/**/*.js", "package.json"]],
];
let passed = true;
for (const [leg, patterns] of legs) {
  const result = await analyzePackage(root, patterns);
  console.log(`${result.passed ? "✓" : "✗"} scan of the ${leg}${result.passed ? "" : `: ${result.message}`}`);
  if (result.details) console.log(result.details);
  passed &&= result.passed;
}
process.exitCode = passed ? 0 : 1;
