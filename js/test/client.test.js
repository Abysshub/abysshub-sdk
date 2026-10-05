import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { Abyss, AbyssError } from "../dist/index.js";

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
