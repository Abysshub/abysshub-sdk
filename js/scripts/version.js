// Writes package.json's version into src/version.ts before tsc, so a build carries
// the version release.yml stamps with `npm version` (prepack builds after it).
import { readFile, writeFile } from "node:fs/promises";

const { version } = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
await writeFile(
  new URL("../src/version.ts", import.meta.url),
  `/** This package's version, written from package.json by scripts/version.js at build. */\nexport const VERSION = ${JSON.stringify(version)};\n`,
);
