import assert from "node:assert/strict";
import { createReadStream } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { Abyss, AbyssError, file } from "../dist/index.js";
import { withFiles } from "./caller.js";
import { loadExchanges, replay } from "./fake-server.js";

const KEY = "abyss_sk_fake_for_tests";
const recordings = Object.fromEntries((await loadExchanges()).map((recording) => [recording.name, recording]));

async function against(recording, work) {
  const server = await replay(recording, { key: KEY });
  try {
    await withFiles(recording.call.files ?? {}, (dir) => work(new Abyss({ apiKey: KEY, baseURL: server.base }), dir));
    assert.deepEqual(server.problems, []);
    assert.equal(server.remaining(), 0, "every recorded request was sent");
  } finally {
    await server.close();
  }
}

const upload = recordings["files-upload-press.json"];
const content = upload.call.files["report.pdf"];
const sources = {
  "a Blob": () => file(new Blob([content]), { filename: "report.pdf" }),
  "a File": () => new File([content], "report.pdf"),
  "a Buffer": () => file(Buffer.from(content), { filename: "report.pdf" }),
  "a Uint8Array": () => file(new TextEncoder().encode(content), { filename: "report.pdf" }),
  "a web stream": () => file(new Blob([content]).stream(), { filename: "report.pdf" }),
  "a file stream": (dir) => createReadStream(join(dir, "report.pdf")),
};

for (const [kind, source] of Object.entries(sources)) {
  test(`${kind} uploads like file(path)`, () =>
    against(upload, async (abyss, dir) => {
      const run = await abyss.run(upload.call.widget, { report: source(dir) });
      assert.equal(run.status, "succeeded");
    }));
}

test("the caller's input is never changed", () =>
  against(upload, async (abyss, dir) => {
    const input = { report: file(join(dir, "report.pdf")) };
    const before = input.report;
    await abyss.run(upload.call.widget, input);
    assert.equal(input.report, before);
  }));

const expired = recordings["files-output-expired.json"];

test("each output file has save() and read(), refreshing an expired URL once", () =>
  against(expired, async (abyss, dir) => {
    const run = await abyss.run(expired.call.widget, expired.call.input);
    const [chart, output] = run.output_files;
    const path = join(dir, "deep", "chart.png");
    assert.equal(await chart.save(path), path);
    assert.equal(await readFile(path, "utf8"), expired.outcome.saved["charts/a.png"]);
    const bytes = await output.read();
    assert.ok(bytes instanceof Uint8Array);
    assert.equal(new TextDecoder().decode(bytes), expired.outcome.saved["output.json"]);
  }));

test("a URL still refused after the refresh raises", () => {
  const recording = structuredClone(expired);
  recording.exchanges = recording.exchanges.slice(0, 3);
  recording.exchanges.push(structuredClone(recording.exchanges[1]));
  recording.exchanges[3].request.path = recording.exchanges[3].request.path.replace("expired", "fresh");
  return against(recording, async (abyss) => {
    const run = await abyss.run(expired.call.widget, expired.call.input);
    await assert.rejects(run.output_files[0].read(), (error) => error instanceof AbyssError && error.status === 403);
  });
});

test("run.save() refuses an output path that leaves its folder", () => {
  const recording = structuredClone(expired);
  recording.exchanges = recording.exchanges.slice(0, 1);
  recording.exchanges[0].response.body.output_files[0].path = "../escape.png";
  return against(recording, async (abyss, dir) => {
    const run = await abyss.run(expired.call.widget, expired.call.input);
    await assert.rejects(run.save(join(dir, "output")), (error) => error instanceof AbyssError);
  });
});
