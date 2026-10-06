import assert from "node:assert/strict";
import { test } from "node:test";
import { Abyss, AbyssError } from "../dist/index.js";
import { timeoutOnceHeld } from "./caller.js";
import { loadExchanges, replay } from "./fake-server.js";

const KEY = "abyss_sk_fake_for_tests";
const recordings = await loadExchanges();
const recording = recordings.find(({ name }) => name === "timeout-reattach.json");
const pressHold = recordings.find(({ name }) => name === "timeout-press-hold.json");
const { widget, input } = recording.call;
const { id } = recording.outcome.error.run;

async function against(work, { served = recording.exchanges.length, from = recording } = {}) {
  const server = await replay(from, { key: KEY });
  try {
    await work(server.base, server);
    assert.deepEqual(server.problems, []);
    assert.equal(from.exchanges.length - server.remaining(), served, "the requests sent");
  } finally {
    await server.close();
  }
}

const isTimeout = (run) => (error) =>
  error instanceof AbyssError && error.code === "timeout" && (run === null ? error.run === null : error.run?.id === run);

test("an aborted signal stops the waiting, raising timeout with the run as last seen", () =>
  against(async (base, server) => {
    const controller = new AbortController();
    server.held.then(() => controller.abort());
    const abyss = new Abyss({ apiKey: KEY, baseURL: base });
    await assert.rejects(abyss.run(widget, input, { signal: controller.signal }), isTimeout(id));
  }));

test("an aborted signal during the press's first hold raises timeout with the run's id, and sends nothing more", () =>
  against(
    async (base, server) => {
      const controller = new AbortController();
      server.held.then(() => controller.abort());
      const abyss = new Abyss({ apiKey: KEY, baseURL: base });
      const error = await abyss.run(widget, input, { signal: controller.signal }).catch((raised) => raised);
      assert.ok(isTimeout(null)(error), `expected a timeout, got ${error}`);
      assert.equal(error.run_id, pressHold.outcome.error.run_id);
      assert.equal(error.request_id, pressHold.outcome.error.request_id);
    },
    { from: pressHold, served: 1 },
  ));

test("a signal aborted before the call sends nothing", () =>
  against(
    async (base) => {
      const abyss = new Abyss({ apiKey: KEY, baseURL: base });
      await assert.rejects(abyss.run(widget, input, { signal: AbortSignal.abort() }), isTimeout(null));
    },
    { served: 0 },
  ));

test("the client's timeout applies to every call", () =>
  against(async (base, server) => {
    const abyss = new Abyss({ apiKey: KEY, baseURL: base, timeout: 0.3 });
    assert.equal(abyss.timeout, 0.3);
    await assert.rejects(timeoutOnceHeld(server.held, () => abyss.run(widget, input)), isTimeout(id));
  }));
