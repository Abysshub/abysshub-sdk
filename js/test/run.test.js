import assert from "node:assert/strict";
import { test } from "node:test";
import { Abyss, AbyssError } from "../dist/index.js";
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
    try {
      const abyss = new Abyss({ apiKey: KEY, baseURL: server.base });
      const { widget, input, options = {} } = recording.call;
      const outcome = await abyss
        .run(widget, input, { maxPrice: options.max_price, idempotencyKey: options.idempotency_key })
        .then((run) => ({ run }), (error) => ({ error }));

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
    } finally {
      await server.close();
    }
  });
}
