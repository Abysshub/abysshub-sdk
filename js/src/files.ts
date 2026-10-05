import { nodeFS } from "./node.js";
import type { Input } from "./types.js";

/** File data held in memory or streamed: a `Blob` or `File`, a `Buffer` or `Uint8Array`, or a stream. */
export type FileData = Blob | Uint8Array | ReadableStream<Uint8Array> | AsyncIterable<Uint8Array | string>;

export interface FileOptions {
  /** The name to upload under. Defaults to the path's or the `File`'s name, else the Field's name. */
  filename?: string;
}

/** A file for a file Field: a path, read when it is uploaded, or data. Made by `file()`. */
export class InputFile {
  readonly source: string | FileData;
  readonly filename: string | undefined;

  constructor(source: string | FileData, options: FileOptions = {}) {
    this.source = source;
    this.filename = options.filename;
  }
}

/** A file for a file Field. A string is a path, read when the file is uploaded. */
export function file(source: string | FileData, options: FileOptions = {}): InputFile {
  return new InputFile(source, options);
}

/** Uploads one file for a Field and answers the upload's id. */
export type Uploader = (field: string, filename: string, data: Blob) => Promise<string>;

/**
 * Uploads every file value in the input, in parallel, and answers the input with each
 * one replaced by its upload's id. Strings pass through as an `https` URL or an upload
 * id, and a list may mix all kinds. The caller's input is never changed.
 */
export async function uploadFiles(input: Input, upload: Uploader): Promise<Input> {
  const uploaded: Input = { ...input };
  const uploads: Promise<void>[] = [];
  const uploadOne = async (field: string, value: InputFile | FileData) => {
    const { filename, data } = await load(value, field);
    return upload(field, filename, data);
  };
  for (const [field, value] of Object.entries(input)) {
    if (isFile(value)) {
      uploads.push(uploadOne(field, value).then((id) => void (uploaded[field] = id)));
    } else if (Array.isArray(value) && value.some(isFile)) {
      const list: unknown[] = [...value];
      uploaded[field] = list;
      list.forEach((item, index) => {
        if (isFile(item)) uploads.push(uploadOne(field, item).then((id) => void (list[index] = id)));
      });
    }
  }
  const failed = (await Promise.allSettled(uploads)).find((settled) => settled.status === "rejected");
  if (failed) throw failed.reason;
  return uploaded;
}

function isFile(value: unknown): value is InputFile | FileData {
  return (
    value instanceof InputFile ||
    value instanceof Blob ||
    value instanceof Uint8Array ||
    value instanceof ReadableStream ||
    (typeof value === "object" && value !== null && Symbol.asyncIterator in value)
  );
}

async function load(value: InputFile | FileData, field: string): Promise<{ filename: string; data: Blob }> {
  const given = value instanceof InputFile ? value : new InputFile(value);
  const { source } = given;
  if (typeof source === "string") {
    const fs = await nodeFS();
    return { filename: given.filename ?? basename(source), data: new Blob([blobPart(await fs.readFile(source))]) };
  }
  const data = source instanceof Blob ? source : source instanceof Uint8Array ? new Blob([blobPart(source)]) : await drain(source);
  return { filename: given.filename ?? nameOf(source) ?? field, data };
}

/** The name a `File` or a file stream (Node's `fs.createReadStream`) carries. */
function nameOf(source: FileData): string | undefined {
  const named = source as { name?: unknown; path?: unknown };
  if (source instanceof Blob) return typeof named.name === "string" && named.name ? named.name : undefined;
  return typeof named.path === "string" ? basename(named.path) : undefined;
}

async function drain(stream: ReadableStream<Uint8Array> | AsyncIterable<Uint8Array | string>): Promise<Blob> {
  const parts: Uint8Array<ArrayBuffer>[] = [];
  const encoder = new TextEncoder();
  const add = (chunk: Uint8Array | string) => parts.push(typeof chunk === "string" ? encoder.encode(chunk) : blobPart(chunk));
  if (stream instanceof ReadableStream) {
    const reader = stream.getReader();
    for (let read = await reader.read(); !read.done; read = await reader.read()) add(read.value);
  } else {
    for await (const chunk of stream) add(chunk);
  }
  return new Blob(parts);
}

/** The bytes as a `Blob` takes them, on a plain `ArrayBuffer`: copied only when they are on a shared one. */
function blobPart(bytes: Uint8Array): Uint8Array<ArrayBuffer> {
  return bytes.buffer instanceof ArrayBuffer ? (bytes as Uint8Array<ArrayBuffer>) : new Uint8Array(bytes);
}

function basename(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}
