// The nightly live run of the JS library (.github/workflows/live.yml). The workflow installs
// the packed library next to this file, the way a caller installs it, then runs it there:
// a few calls against dev's /v1, then the probe Widget's code exactly as its page shows it.
// Each check prints one line; a broken one prints its code and request_id, and the run exits 1.
import Abyss, { AbyssError, file } from "abysshub";
import { createHash } from "node:crypto";
import { mkdtemp, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

/** A key the probe has no Field for, so a press with it is refused as `invalid_input`. */
const NOT_A_FIELD = "abysshub_live_not_a_field";
/** The seconds each call waits at most, so a stuck run turns the night red instead of hanging it. */
const TIMEOUT = 600;

/** A check's own finding: its message says it all, so it prints without a stack. */
class Broke extends Error {}

const here = fileURLToPath(new URL(".", import.meta.url));
config("ABYSS_API_KEY");
const base = config("ABYSS_BASE_URL").replace(/\/+$/, "");
const widget = config("ABYSS_PROBE_WIDGET");
const widgetId = /^widget_([1-9][0-9]*)$/.exec(widget)?.[1];
if (!widgetId) fail(`ABYSS_PROBE_WIDGET is ${JSON.stringify(widget)}, not a listed Widget's widget_<id>.`);

const text = `abysshub live run (js), ${new Date().toISOString()}`;
const sent = `A probe file from ${text}.\n`;
const abyss = new Abyss({ timeout: TIMEOUT });
// Inside this folder, so the Widget's code finds the installed `abysshub` the way a caller's does.
const dir = await mkdtemp(join(here, "live-"));
const runs = [];
let failures = 0;

try {
  await check("run() with a JSON input", async () => ran(await abyss.run(widget, { text })));

  await check("run() with a file input", async () => {
    const path = join(dir, "probe.txt");
    await writeFile(path, sent);
    const run = await abyss.run(widget, { text, file: file(path) });
    const echoed = run.result?.file?.sha256;
    if (echoed !== sha256(sent)) throw new Broke(`${run.id}: the probe got a file with sha256 ${echoed}, not the one sent`);
    return ran(run);
  });

  await check("run.save()", async () => {
    if (runs.length === 0) throw new Broke("no run to save: both presses broke");
    let saved = 0;
    for (const run of runs) {
      const into = join(dir, "saved", run.id);
      saved += (await run.save(into)).length;
      for (const output of run.output_files) {
        const { size } = await stat(join(into, output.path));
        if (size !== output.size) throw new Broke(`${run.id}: ${output.path} saved ${size} bytes, its run says ${output.size}`);
      }
      const echo = await readFile(join(into, "echo.txt"), "utf8");
      if (echo !== `${text}\n`) throw new Broke(`${run.id}: echo.txt holds ${JSON.stringify(echo)}, not the text sent`);
    }
    return `${saved} file(s) saved from ${runs.length} run(s), each at its size`;
  });

  await check("a refusal (invalid_input)", async () => {
    try {
      await abyss.run(widget, { text, [NOT_A_FIELD]: true });
    } catch (error) {
      if (!(error instanceof AbyssError) || error.code !== "invalid_input") throw error;
      if (!error.request_id) throw new Broke("the refusal carries no request_id");
      return `status ${error.status}, param ${error.param}, request_id ${error.request_id}`;
    }
    throw new Broke(`a press with the key ${NOT_A_FIELD} was not refused`);
  });

  await check("the Widget's code from its page", async () => {
    const page = `${base}/api/products/${widgetId}/api-access`;
    const response = await fetch(page, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Broke(`GET ${page} answered ${response.status}${response.status === 403 ? " (with no JSON body, that is dev's WAF)" : ""}`);
    const code = (await response.json()).data.javascript;
    const at = await mkdtemp(join(dir, "panel-"));
    for (const [, name] of code.matchAll(/\bfile\("([^"]+)"\)/g)) await writeFile(join(at, name), sent);
    await writeFile(join(at, "panel.mjs"), code);
    process.chdir(at);
    try {
      await import(pathToFileURL(join(at, "panel.mjs")).href);
    } finally {
      process.chdir(here);
    }
    if (!code.includes("run.save(")) return `${code.split("\n").length} lines ran`;
    const saved = (await readdir(join(at, "output"), { recursive: true, withFileTypes: true })).filter((entry) => entry.isFile());
    if (saved.length === 0) throw new Broke("the code saves the outputs, and none were saved");
    return `${code.split("\n").length} lines ran and saved ${saved.length} file(s)`;
  });
} finally {
  await rm(dir, { recursive: true, force: true });
}

if (failures > 0) fail(`${failures} of 5 checks broke.`);

async function check(name, call) {
  try {
    console.log(`ok   ${name}: ${await call()}`);
  } catch (error) {
    failures++;
    console.log(`::error::${name}: ${describe(error)}`);
  }
}

function ran(run) {
  runs.push(run);
  return `${run.id} ${run.status}, price ${run.price}, ${run.output_files.length} output file(s)`;
}

function describe(error) {
  if (error instanceof Broke) return error.message;
  if (!(error instanceof AbyssError)) return error?.stack ?? String(error);
  const run = error.run ? `, run ${error.run.id}` : "";
  return `${error.code} (status ${error.status}, request_id ${error.request_id}${run}): ${error.message}`;
}

function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

function config(name) {
  const value = process.env[name];
  if (!value) fail(`${name} is not set (see .github/workflows/live.yml).`);
  return value;
}

function fail(message) {
  console.log(`::error::${message}`);
  process.exit(1);
}
