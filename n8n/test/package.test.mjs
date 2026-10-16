import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));

test("n8n-nodes-abysshub is MIT, with no runtime dependencies and n8n-workflow only as a peer", () => {
  assert.equal(pkg.name, "n8n-nodes-abysshub");
  assert.equal(pkg.license, "MIT");
  assert.deepEqual(Object.keys(pkg.dependencies ?? {}), []);
  assert.deepEqual(pkg.peerDependencies, { "n8n-workflow": "*" });
  assert.ok(pkg.keywords.includes("n8n-community-node-package"));
});

test("the package names the node and credential n8n loads", () => {
  assert.deepEqual(pkg.n8n.nodes, ["dist/nodes/Abyss/Abyss.node.js"]);
  assert.deepEqual(pkg.n8n.credentials, ["dist/credentials/AbyssApi.credentials.js"]);
});

// Publishing waits for the /v1 cutover: until then nothing may publish the package.
test("nothing publishes the package yet", async () => {
  assert.equal(pkg.private, true, "npm refuses to publish a private package");
  const release = await readFile(new URL("../../.github/workflows/release.yml", import.meta.url), "utf8");
  assert.doesNotMatch(release, /n8n/, "release.yml does not name n8n/");
  const directories = [...release.matchAll(/working-directory:\s*(\S+)/g)].map(([, dir]) => dir);
  assert.deepEqual([...new Set(directories)], ["js"]);
});
