import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const repo = fileURLToPath(new URL("../../", import.meta.url));
const claude = fileURLToPath(new URL("../node_modules/.bin/claude", import.meta.url));

test("the repo passes Claude Code's plugin marketplace validator in strict mode", async () => {
  const config = await mkdtemp(join(tmpdir(), "claude-"));
  try {
    const { stdout } = await promisify(execFile)(claude, ["plugin", "validate", "--strict", "--json", repo], {
      env: { ...process.env, CLAUDE_CONFIG_DIR: config },
    });
    const report = JSON.parse(stdout);
    assert.equal(report.success, true);
    assert.equal(report.manifest.type, "marketplace");
  } finally {
    await rm(config, { recursive: true, force: true });
  }
});

test("the abyss-widget plugin's skill is the repo's skills/abyss-widget", async () => {
  const marketplace = JSON.parse(await readFile(join(repo, ".claude-plugin/marketplace.json"), "utf8"));
  const plugin = marketplace.plugins.find((p) => p.name === "abyss-widget");
  assert.equal(plugin.source, "./");
  assert.deepEqual(plugin.skills, ["./skills/abyss-widget"]);
  assert.ok((await stat(join(repo, plugin.skills[0], "SKILL.md"))).isFile());
});
