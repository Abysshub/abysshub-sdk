import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { Abyss, AbyssError } from "../dist/index.js";
import { Run } from "../dist/run.js";
import { callerInput, perform, withFiles } from "./caller.js";
import { loadExchanges, replay } from "./fake-server.js";

const KEY = "abyss_sk_fake_for_tests";

// The fields `expected` names, however deep: a list must have its length, and an
// object at least the fields it names.
function assertFields(actual, expected, where) {
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${where} is a list`);
    assert.equal(actual.length, expected.length, `${where}.length`);
    expected.forEach((item, index) => assertFields(actual[index], item, `${where}[${index}]`));
  } else if (expected && typeof expected === "object") {
    assert.ok(actual && typeof actual === "object", `${where} is an object`);
    for (const [name, value] of Object.entries(expected)) assertFields(actual[name], value, `${where}.${name}`);
  } else {
    assert.equal(actual, expected, where);
  }
}

for (const recording of await loadExchanges()) {
  const { method = "run", input = {}, files = {}, save, client = {} } = recording.call;
  test(`${method}(): ${recording.name}`, async () => {
    const server = await replay(recording, { key: KEY });
    try {
      await withFiles(files, async (dir) => {
        const abyss = new Abyss({ apiKey: KEY, baseURL: server.base, maxRetries: client.max_retries });
        const outcome = await perform(abyss, recording.call, callerInput(input, dir, files)).then(
          (value) => ({ value }),
          (error) => ({ error }),
        );
        const saved = save && outcome.value ? await outcome.value.save(join(dir, save)) : null;

        assert.deepEqual(server.problems, []);
        assert.equal(server.remaining(), 0, "every recorded request was sent");
        if (recording.outcome.run) {
          assert.ok(outcome.value instanceof Run, `expected a run, got ${outcome.error ?? outcome.value}`);
          assertFields(outcome.value, recording.outcome.run, "run");
        } else if (recording.outcome.value) {
          assert.ok(outcome.value, `expected a value, got ${outcome.error}`);
          assertFields(outcome.value, recording.outcome.value, "value");
        } else {
          assert.ok(outcome.error instanceof AbyssError, `expected an AbyssError, got ${outcome.error ?? outcome.value}`);
          const { run, ...fields } = recording.outcome.error;
          assertFields(outcome.error, fields, "error");
          if (run === null) assert.equal(outcome.error.run, null);
          else assertFields(outcome.error.run, run, "error.run");
        }
        if (recording.outcome.saved) {
          const expected = Object.keys(recording.outcome.saved).map((path) => join(dir, save, path));
          assert.deepEqual(saved, expected, "run.save() answers the paths it wrote");
          for (const [path, content] of Object.entries(recording.outcome.saved)) {
            assert.equal(await readFile(join(dir, save, path), "utf8"), content, `saved ${path}`);
          }
        }
      });
    } finally {
      await server.close();
    }
  });
}
