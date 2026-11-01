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

// release.yml publishes the package beside the JS one. n8n verifies only a package with
// provenance, and npm accepts provenance only when `repository` names this repo.
test("the package publishes its build from this repo, with provenance", () => {
  assert.equal(pkg.private, undefined, "npm refuses to publish a private package");
  assert.equal(pkg.version, "0.0.0", "release.yml computes every version");
  assert.equal(pkg.repository.url, "git+https://github.com/Abysshub/abysshub-sdk.git");
  assert.equal(pkg.repository.directory, "n8n");
  assert.deepEqual(pkg.files, ["dist"]);
  assert.equal(pkg.publishConfig?.provenance, true);
});
