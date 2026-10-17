// The node replays the recorded exchanges in exchanges/ whose call is one of its
// operations, through the libraries' fake server, so every request it sends and every
// answer it reads is one the contract allows (js/test/exchanges.test.js checks them).
import assert from "node:assert/strict";
import { test } from "node:test";
import { loadExchanges, replay } from "../../js/test/fake-server.js";
import { AbyssApi, authenticated, execute, httpRequest, resolve } from "./n8n.mjs";

const KEY = "abyss_sk_fake_for_tests";

/** The recordings the node replays, each with the parameters its call is made with. */
const OPERATIONS = {
  "files-asleep-save.json": (call) => ({ operation: "get", runId: call.id, downloadOutputFiles: true }),
  "files-output-expired.json": (call) => ({ ...press(call), downloadOutputFiles: true }),
  "files-waking-save.json": (call) => ({ operation: "get", runId: call.id, downloadOutputFiles: true }),
  "retry-409.json": press,
  "retry-429.json": press,
  "retry-5xx-third-fails.json": press,
  "retry-5xx.json": press,
  "retry-drop-third-fails.json": press,
  "retry-drop.json": press,
  "run-held-failure.json": press,
  "run-held-success.json": press,
  "run-holds-full-202.json": press,
  "run-hour-running-reattach.json": press,
  "run-input-https-link.json": press,
  "run-options.json": press,
  "run-reattach-again.json": press,
  "run-refused-insufficient-funds.json": press,
  "run-refused-invalid-input.json": press,
  "run-refused-price-above-max.json": press,
  "runs-create.json": (call) => ({ ...press(call), waitForResult: false }),
  "runs-get.json": (call) => ({ operation: "get", runId: call.id }),
};

/** A recorded `run` or `runs.create`, as the Run a Widget operation's parameters. */
function press(call) {
  const options = {};
  if (call.options?.max_price !== undefined) options.maxPrice = call.options.max_price;
  if (call.options?.idempotency_key !== undefined) options.idempotencyKey = call.options.idempotency_key;
  return { operation: "run", widgetId: call.widget, input: JSON.stringify(call.input ?? {}), options };
}

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

/** Replays `recording` through the node, made with `parameters`, and answers its output or its error. */
async function replayNode(recording, parameters, extra = {}) {
  const server = await replay(recording, { key: KEY });
  try {
    const outcome = await execute({ parameters, credentials: { apiKey: KEY, url: server.base }, ...extra }).then(
      (items) => ({ items }),
      (error) => ({ error }),
    );
    assert.deepEqual(server.problems, []);
    assert.equal(server.remaining(), 0, "every recorded request was sent");
    return outcome;
  } finally {
    await server.close();
  }
}

const recordings = await loadExchanges();
const byName = Object.fromEntries(recordings.map((recording) => [recording.name, recording]));

for (const [name, parameters] of Object.entries(OPERATIONS)) {
  const recording = byName[name];
  test(`${parameters(recording.call).operation}: ${name}`, async () => {
    const { items, error } = await replayNode(recording, parameters(recording.call));
    const { outcome } = recording;
    if (outcome.run && !outcome.save_error) {
      assert.ok(items, `expected a run, got ${error}`);
      assert.equal(items.length, 1);
      assertFields(items[0].json, outcome.run, "run");
      assert.deepEqual(items[0].pairedItem, { item: 0 });
    }
    if (outcome.error) {
      assert.ok(error, "expected an n8n error");
      assert.match(error.constructor.name, /^Node(Api|Operation)Error$/);
      if (outcome.error.message) assert.equal(error.message, outcome.error.message, "the API's message");
      // `connection_error` is the libraries' own code for a drop; /v1 sends no code then.
      if (outcome.error.code && outcome.error.code !== "connection_error") {
        assert.ok(error.description.includes(outcome.error.code), `the description names ${outcome.error.code}`);
      }
      if (outcome.error.request_id) assert.ok(error.description.includes(outcome.error.request_id), "the request id");
    }
    if (outcome.save_error) {
      assert.ok(error, "expected the download to raise");
      assert.equal(error.description, outcome.save_error.code);
    }
    if (outcome.saved) {
      const binary = items[0].binary;
      const paths = Object.keys(outcome.saved);
      assert.deepEqual(Object.keys(binary), paths.map((_, index) => `file_${index}`));
      paths.forEach((path, index) => {
        const file = binary[`file_${index}`];
        assert.equal(Buffer.from(file.data, "base64").toString("utf8"), outcome.saved[path], `downloaded ${path}`);
        assert.equal(file.fileName, path.split("/").at(-1));
      });
    }
  });
}

test("the credential test reads GET /v1/key with the credential's key and URL", async () => {
  const recording = byName["key.json"];
  const server = await replay(recording, { key: KEY });
  try {
    const credentials = { apiKey: KEY, url: server.base };
    const { request } = new AbyssApi().test;
    const answer = await httpRequest(
      authenticated({ ...request, baseURL: resolve(request.baseURL, credentials), json: true, returnFullResponse: true }, credentials),
    );
    assert.equal(answer.statusCode, 200);
    assertFields(answer.body, recording.outcome.value, "key");
    assert.deepEqual(server.problems, []);
    assert.equal(server.remaining(), 0);
  } finally {
    await server.close();
  }
});

test("the credential's API URL defaults to the production API", () => {
  const url = new AbyssApi().properties.find(({ name }) => name === "url");
  assert.equal(url.default, "https://api.abysshub.com");
});

test("a hold cut after its headers is pressed again with the same Idempotency-Key, and holds again", async () => {
  // The press cut in run-cut-reattach.json, then the same press answering the run its re-attach read.
  const cut = byName["run-cut-reattach.json"];
  const [cutPress, reattach] = cut.exchanges;
  const recording = { ...cut, exchanges: [cutPress, { request: cutPress.request, response: reattach.response }] };
  const { items, error } = await replayNode(recording, { operation: "run", widgetId: cut.call.widget, input: cut.call.input });
  assert.ok(items, `expected a run, got ${error}`);
  assertFields(items[0].json, cut.outcome.run, "run");
});

test("a refusal with Continue On Fail on becomes an item carrying the API's message", async () => {
  const recording = byName["run-refused-invalid-input.json"];
  const { items } = await replayNode(recording, press(recording.call), { continueOnFail: true });
  assert.deepEqual(items, [{ json: { error: recording.outcome.error.message }, pairedItem: { item: 0 } }]);
});

test("each input item is its own run, pressed with an Idempotency-Key of its own", async () => {
  const one = byName["run-held-success.json"];
  const two = byName["run-input-https-link.json"];
  const server = await replay({ exchanges: [...one.exchanges, ...two.exchanges] }, { key: KEY });
  try {
    const output = await execute({
      parameters: ({ json }) => ({ operation: "run", widgetId: json.widget, input: json.input }),
      credentials: { apiKey: KEY, url: server.base },
      items: [one, two].map(({ call }) => ({ json: call })),
    });
    // The fake server expects one key per recording, so the second press's own key is its one complaint.
    assert.equal(server.problems.length, 1);
    assert.match(server.problems[0], /^#2: header Idempotency-Key is "[0-9a-f-]{36}"$/);
    assert.deepEqual(
      output.map(({ json, pairedItem }) => [json.id, pairedItem.item]),
      [
        [one.outcome.run.id, 0],
        [two.outcome.run.id, 1],
      ],
    );
  } finally {
    await server.close();
  }
});

test("an input that is not a JSON object is refused before anything is sent", async () => {
  for (const input of ["[1, 2]", "{not json", "42"]) {
    await assert.rejects(
      execute({ parameters: { operation: "run", widgetId: "widget_131", input }, credentials: { apiKey: KEY, url: "http://127.0.0.1:9" } }),
      (error) => error.constructor.name === "NodeOperationError" && /JSON object/.test(error.message),
    );
  }
});

test("a Field's name is sent as it is", async () => {
  const base = byName["run-held-success.json"];
  const input = { "Loan Amount": 250000, camelCase_field: true };
  const recording = structuredClone(base);
  recording.exchanges[0].request.body = { input };
  const { items, error } = await replayNode(recording, { operation: "run", widgetId: base.call.widget, input: JSON.stringify(input) });
  assert.ok(items, `expected a run, got ${error}`);
});
