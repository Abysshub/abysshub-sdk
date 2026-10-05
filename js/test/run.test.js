import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { Abyss, AbyssError } from "../dist/index.js";
import { callerInput, withFiles } from "./caller.js";
import { loadExchanges, replay } from "./fake-server.js";

const KEY = "abyss_sk_fake_for_tests";

function assertFields(actual, expected, where) {
  for (const [name, value] of Object.entries(expected)) {
    assert.deepEqual(actual[name], value, `${where}.${name}`);
  }
}

for (const recording of await loadExchanges()) {
  test(`run(): ${recording.name}`, async () => {
    const server = await replay(recording, { key: KEY });
    const { widget, input, options = {}, files = {}, save } = recording.call;
    try {
      await withFiles(files, async (dir) => {
        const abyss = new Abyss({ apiKey: KEY, baseURL: server.base });
        const outcome = await abyss
          .run(widget, callerInput(input, dir, files), {
            maxPrice: options.max_price,
            idempotencyKey: options.idempotency_key,
          })
          .then((run) => ({ run }), (error) => ({ error }));
        const saved = save && outcome.run ? await outcome.run.save(join(dir, save)) : null;

        assert.deepEqual(server.problems, []);
        assert.equal(server.remaining(), 0, "every recorded request was sent");
        if (recording.outcome.run) {
          assert.ok(outcome.run, `expected a run, got ${outcome.error}`);
          assertFields(outcome.run, recording.outcome.run, "run");
        } else {
          assert.ok(outcome.error instanceof AbyssError, `expected an AbyssError, got ${outcome.error ?? "a run"}`);
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
