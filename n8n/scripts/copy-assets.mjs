// Copies the icons and codex files beside the compiled nodes and credentials, where n8n reads them.
import { cp, readdir } from "node:fs/promises";

for (const dir of ["credentials", "nodes"]) {
  const root = new URL(`../${dir}/`, import.meta.url);
  for (const entry of await readdir(root, { recursive: true })) {
    if (/\.(svg|json)$/.test(entry)) await cp(new URL(entry, root), new URL(`../dist/${dir}/${entry}`, import.meta.url));
  }
}
