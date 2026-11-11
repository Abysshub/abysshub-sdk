import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

test("abysshub has no runtime dependencies", async () => {
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(pkg.name, "abysshub");
  assert.deepEqual(Object.keys(pkg.dependencies ?? {}), []);
});

test("abysshub's npm page says the job, carries keywords and links to the Docs", async () => {
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.match(pkg.description, /Abyss Widget/);
  assert.ok(["abyss", "abysshub", "widget"].every((word) => pkg.keywords.includes(word)));
  assert.equal(pkg.homepage, "https://abysshub.com/docs#api");
  assert.equal(pkg.repository.url, "git+https://github.com/Abysshub/abysshub-sdk.git");
});
