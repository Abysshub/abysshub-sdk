// Packs the package and installs the tarball in a clean folder, then loads it the way
// each Widget's page writes it, `import Abyss, { file } from "abysshub"`, and the way a
// CommonJS caller does, `const { Abyss, file } = require("abysshub")`.
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const pkgDir = fileURLToPath(new URL("..", import.meta.url));
const tsc = fileURLToPath(new URL("../node_modules/typescript/bin/tsc", import.meta.url));

let caller;

before(async () => {
  caller = await mkdtemp(join(tmpdir(), "abysshub-packed-"));
  // npm test has just built dist/, so the pack skips prepack's second build.
  await run(npm, ["pack", "--ignore-scripts", "--pack-destination", caller], { cwd: pkgDir });
  const tarball = (await readdir(caller)).find((name) => name.endsWith(".tgz"));
  assert.ok(tarball, "npm pack wrote no tarball");
  await writeFile(join(caller, "package.json"), JSON.stringify({ name: "caller", private: true, type: "module" }));
  await run(npm, ["install", "--offline", "--no-audit", "--no-fund", "--ignore-scripts", `./${tarball}`], { cwd: caller });
});

after(async () => {
  if (caller) await rm(caller, { recursive: true, force: true });
});

test("the packed package runs the import each Widget's page shows", async () => {
  await writeFile(
    join(caller, "panel.js"),
    [
      'import Abyss, { file } from "abysshub";',
      'import { Abyss as Named, file as namedFile } from "abysshub";',
      'const abyss = new Abyss({ apiKey: "abyss_sk_dev_test" });',
      "if (Abyss !== Named) throw new Error('the default Abyss is not the named Abyss');",
      "if (typeof abyss.run !== 'function') throw new Error('abyss.run is not a function');",
      "if (file !== namedFile) throw new Error('file differs');",
      'console.log("ok");',
    ].join("\n"),
  );
  const { stdout } = await run(process.execPath, ["panel.js"], { cwd: caller });
  assert.equal(stdout.trim(), "ok");
});

test("TypeScript type-checks the default import of the packed package", async () => {
  await writeFile(
    join(caller, "panel.ts"),
    [
      'import Abyss, { Abyss as Named, file, type Run } from "abysshub";',
      'const abyss: Named = new Abyss({ apiKey: "abyss_sk_dev_test" });',
      'const pending: Promise<Run> = abyss.run("widget_1660", { input_pdf: file("report.pdf") });',
      "void pending;",
    ].join("\n"),
  );
  await writeFile(
    join(caller, "tsconfig.json"),
    JSON.stringify({
      compilerOptions: {
        target: "ES2022",
        lib: ["ES2022", "DOM"],
        module: "NodeNext",
        moduleResolution: "NodeNext",
        strict: true,
        noEmit: true,
        types: [],
      },
      files: ["panel.ts"],
    }),
  );
  await run(process.execPath, [tsc, "-p", "tsconfig.json"], { cwd: caller });
});

test("the packed package loads with require() from a CommonJS file", async () => {
  await writeFile(
    join(caller, "panel.cjs"),
    [
      'const { Abyss, file } = require("abysshub");',
      'const mod = require("abysshub");',
      "if (Abyss !== mod.default) throw new Error('Abyss is not the module default');",
      "if (typeof file !== 'function') throw new Error('file is not a function');",
      'const abyss = new Abyss({ apiKey: "abyss_sk_dev_test" });',
      "if (typeof abyss.run !== 'function') throw new Error('abyss.run is not a function');",
      'console.log("ok");',
    ].join("\n"),
  );
  const { stdout } = await run(process.execPath, ["panel.cjs"], { cwd: caller });
  assert.equal(stdout.trim(), "ok");
});

test("TypeScript type-checks a CommonJS require of the packed package", async () => {
  await writeFile(
    join(caller, "panel.cts"),
    [
      'import abysshub = require("abysshub");',
      'const abyss: abysshub.Abyss = new abysshub.Abyss({ apiKey: "abyss_sk_dev_test" });',
      'const pending: Promise<abysshub.Run> = abyss.run("widget_1660", { input_pdf: abysshub.file("report.pdf") });',
      "void pending;",
    ].join("\n"),
  );
  await writeFile(
    join(caller, "tsconfig.cjs.json"),
    JSON.stringify({
      compilerOptions: {
        target: "ES2022",
        lib: ["ES2022", "DOM"],
        module: "NodeNext",
        moduleResolution: "NodeNext",
        strict: true,
        noEmit: true,
        types: [],
      },
      files: ["panel.cts"],
    }),
  );
  await run(process.execPath, [tsc, "-p", "tsconfig.cjs.json"], { cwd: caller });
});
