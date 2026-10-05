// What a recorded call's caller holds: its files on disk, and its input as a caller writes it.
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { file } from "../dist/index.js";

/** The caller's input: `{"$file": name}` is `file(path)`, and `{"$bytes": name}` a `File` in memory. */
export function callerInput(input, dir, files) {
  const value = (item) => {
    if (item?.$file) return file(join(dir, item.$file));
    if (item?.$bytes) return new File([files[item.$bytes]], item.$bytes);
    return item;
  };
  return Object.fromEntries(
    Object.entries(input).map(([field, item]) => [field, Array.isArray(item) ? item.map(value) : value(item)]),
  );
}

export async function withFiles(files, work) {
  const dir = await mkdtemp(join(tmpdir(), "abysshub-"));
  try {
    for (const [name, content] of Object.entries(files)) await writeFile(join(dir, name), content);
    return await work(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
