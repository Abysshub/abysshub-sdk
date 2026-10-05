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

/** The recorded call, made through the method it names, with its options in JS's spelling. */
export function perform(abyss, call, input) {
  const { timeout, ...options } = call.options ?? {};
  const waiting = { timeout };
  switch (call.method ?? "run") {
    case "run":
    case "runs.create": {
      const press = call.method === "runs.create" ? abyss.runs.create : abyss.run.bind(abyss);
      return press(call.widget, input, { maxPrice: options.max_price, idempotencyKey: options.idempotency_key, ...waiting });
    }
    case "runs.get":
      return abyss.runs.get(call.id, { wait: options.wait, ...waiting });
    case "runs.list":
      return abyss.runs.list({ limit: options.limit, startingAfter: options.starting_after, ...waiting });
    case "widgets.get":
      return abyss.widgets.get(call.widget, waiting);
    case "uploads.create":
      return abyss.uploads.create(call.widget, options, waiting);
    case "key":
      return abyss.key(waiting);
    default:
      throw new Error(`no such method: ${call.method}`);
  }
}
