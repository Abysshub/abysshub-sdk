import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { afterEach, beforeEach, test } from "node:test";
import { Abyss, AbyssError } from "../dist/index.js";
import { loadExchanges, replay } from "./fake-server.js";

const NAMES = ["ABYSS_API_KEY", "ABYSS_BASE_URL"];
let saved;

beforeEach(() => {
  saved = Object.fromEntries(NAMES.map((name) => [name, process.env[name]]));
  for (const name of NAMES) delete process.env[name];
});

afterEach(() => {
  for (const name of NAMES) {
    if (saved[name] === undefined) delete process.env[name];
    else process.env[name] = saved[name];
  }
});

test("a key goes to the api's address", () => {
  assert.equal(new Abyss({ apiKey: "abyss_sk_x" }).baseURL, "https://api.abysshub.com");
});

test("an abyss_sk_dev_ key goes to dev's address", () => {
  assert.equal(new Abyss({ apiKey: "abyss_sk_dev_x" }).baseURL, "https://api.dev.abysshub.com");
});

test("ABYSS_BASE_URL overrides the key's address, and baseURL overrides both", () => {
  process.env.ABYSS_BASE_URL = "http://localhost:8000/";
  assert.equal(new Abyss({ apiKey: "abyss_sk_dev_x" }).baseURL, "http://localhost:8000");
  assert.equal(new Abyss({ apiKey: "abyss_sk_dev_x", baseURL: "http://other" }).baseURL, "http://other");
});

test("the key comes from ABYSS_API_KEY", () => {
  process.env.ABYSS_API_KEY = "abyss_sk_dev_x";
  assert.equal(new Abyss().baseURL, "https://api.dev.abysshub.com");
});

test("no key raises AbyssError", () => {
  assert.throws(() => new Abyss(), (error) => error instanceof AbyssError && error.code === "invalid_api_key");
});

test("maxRetries defaults to 2", () => {
  assert.equal(new Abyss({ apiKey: "abyss_sk_x" }).maxRetries, 2);
  assert.equal(new Abyss({ apiKey: "abyss_sk_x", maxRetries: 0 }).maxRetries, 0);
});

test("in a browser, new Abyss() throws", () => {
  globalThis.window = globalThis;
  globalThis.document = {};
  try {
    assert.throws(
      () => new Abyss({ apiKey: "abyss_sk_x" }),
      { message: "An Abyss API key is a server-side secret. Call the API from your server." },
    );
  } finally {
    delete globalThis.window;
    delete globalThis.document;
  }
});

test("every request sends the User-Agent", async () => {
  const agents = [];
  const server = createServer((req, res) => {
    agents.push(req.headers["user-agent"]);
    res.writeHead(200, { "Content-Type": "application/json" }).end('{"key":"abyss_sk_…3f9a"}');
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    await new Abyss({ apiKey: "abyss_sk_x", baseURL: `http://127.0.0.1:${server.address().port}` }).key();
    const { version } = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
    assert.deepEqual(agents, [`abysshub-js/${version} (node ${process.versions.node})`]);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});

test("a refusal without shortfall or price carries null for both", async () => {
  const recording = (await loadExchanges()).find(({ name }) => name === "run-refused-invalid-input.json");
  const server = await replay(recording, { key: "abyss_sk_x" });
  try {
    const abyss = new Abyss({ apiKey: "abyss_sk_x", baseURL: server.base });
    await assert.rejects(
      abyss.run(recording.call.widget, recording.call.input),
      (error) => error instanceof AbyssError && error.code === "invalid_input" && error.shortfall === null && error.price === null,
    );
    assert.deepEqual(server.problems, []);
  } finally {
    await server.close();
  }
});
