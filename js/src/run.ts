import { AbyssError } from "./error.js";
import { nodeFS, nodePath } from "./node.js";
import type { RunData, RunError, RunFileData, RunStatus } from "./types.js";

/** Reads the run again with `GET /v1/runs/{id}`. */
export type Reread = () => Promise<RunData>;

/** A file this many bytes or larger downloads as parallel byte ranges: 64 MiB. */
export const RANGED_FROM = 64 * 1024 * 1024;

/** How many parallel byte ranges a large file downloads as. */
export const RANGES = 16;

/** A byte range, its first and last byte included, as a `Range` header names it. */
type Range = [first: number, last: number];

/** The byte ranges a file of `size` bytes downloads as, or null when it downloads whole. */
function ranges(size: number): Range[] | null {
  if (size < RANGED_FROM) return null;
  const step = Math.ceil(size / RANGES);
  const parts: Range[] = [];
  for (let first = 0; first < size; first += step) parts.push([first, Math.min(first + step, size) - 1]);
  return parts;
}

/** A run, with `/v1`'s names. */
export class Run {
  id: string;
  widget: string;
  status: RunStatus;
  price: number;
  result: unknown;
  output_files: RunFile[];
  error: RunError | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  readonly #reread: Reread;

  constructor(data: RunData, reread: Reread) {
    this.id = data.id;
    this.widget = data.widget;
    this.status = data.status;
    this.price = data.price;
    this.result = data.result;
    this.error = data.error;
    this.created_at = data.created_at;
    this.started_at = data.started_at;
    this.ended_at = data.ended_at;
    this.#reread = reread;
    this.output_files = data.output_files.map((output) => new RunFile(output, () => this.#refreshURLs()));
  }

  /** Reads the run again and gives every output file its freshly signed `url`. */
  async #refreshURLs(): Promise<void> {
    const fresh = await this.#reread();
    for (const output of this.output_files) {
      const url = fresh.output_files.find((candidate) => candidate.path === output.path)?.url;
      if (url) output.url = url;
    }
  }

  /** Saves every output file under `dir`, at its `path`, and answers the paths it wrote. */
  async save(dir: string): Promise<string[]> {
    const path = await nodePath();
    const saved: string[] = [];
    for (const output of this.output_files) {
      const target = path.join(dir, output.path);
      const inside = path.relative(path.resolve(dir), path.resolve(target));
      if (!inside || inside.startsWith("..") || path.isAbsolute(inside)) {
        throw new AbyssError({
          code: "unexpected_response",
          message: `The output file ${output.path} would be saved outside ${dir}.`,
        });
      }
      saved.push(await output.save(target));
    }
    return saved;
  }
}

/** One file a run wrote. Its `url` is signed fresh on every read of the run, and expires. */
export class RunFile {
  path: string;
  size: number;
  content_type: string;
  url: string;
  readonly #refresh: () => Promise<void>;

  constructor(data: RunFileData, refresh: () => Promise<void>) {
    this.path = data.path;
    this.size = data.size;
    this.content_type = data.content_type;
    this.url = data.url;
    this.#refresh = refresh;
  }

  /**
   * Downloads the file. An expired `url` is refreshed once, by reading the run again. A
   * file of `RANGED_FROM` bytes or more downloads as `RANGES` parallel byte ranges of its
   * one `url`: the first goes alone, and once it answers 206 the others go together. A
   * storage that ignores `Range` answers the whole file to the first, which is kept.
   */
  async read(): Promise<Uint8Array> {
    const parts = ranges(this.size);
    const stop = new AbortController();
    try {
      let response = await this.#get(parts?.[0], stop.signal);
      if (response.status === 403) {
        await response.body?.cancel();
        await this.#refresh();
        response = await this.#get(parts?.[0], stop.signal);
      }
      if (!response.ok) {
        await response.body?.cancel();
        throw this.#answered(response.status);
      }
      if (!parts || response.status !== 206) return new Uint8Array(await response.arrayBuffer());
      const first = response;
      const reads = parts.map(async (part, index) =>
        this.#part(index === 0 ? first : await this.#get(part, stop.signal), part),
      );
      try {
        const bytes = new Uint8Array(this.size);
        for (const [index, part] of (await Promise.all(reads)).entries()) bytes.set(part, parts[index]![0]);
        return bytes;
      } catch (error) {
        stop.abort();
        await Promise.allSettled(reads);
        throw error;
      }
    } catch (error) {
      if (error instanceof AbyssError) throw error;
      throw new AbyssError({
        code: "connection_error",
        message: "The connection to storage dropped during a download.",
        cause: error,
      });
    }
  }

  /** Fetches the file from storage, without the API key: whole, or the byte range `part`. */
  #get(part: Range | undefined, signal: AbortSignal): Promise<Response> {
    return fetch(this.url, { signal, ...(part ? { headers: { Range: `bytes=${part[0]}-${part[1]}` } } : {}) });
  }

  /** The bytes of one range, which must answer 206 with exactly the range's length. */
  async #part(response: Response, [first, last]: Range): Promise<Uint8Array> {
    if (response.status !== 206) {
      await response.body?.cancel();
      throw this.#answered(response.status);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length !== last - first + 1) {
      throw new AbyssError({
        code: "unexpected_response",
        message: `The download of ${this.path} answered ${bytes.length} bytes for the range ${first}-${last}.`,
        status: response.status,
      });
    }
    return bytes;
  }

  #answered(status: number): AbyssError {
    return new AbyssError({
      code: "unexpected_response",
      message: `The download of ${this.path} answered ${status}.`,
      status,
    });
  }

  /** Downloads the file to `path`, making its folders, and answers `path`. */
  async save(path: string): Promise<string> {
    const [fs, { dirname }] = await Promise.all([nodeFS(), nodePath()]);
    const bytes = await this.read();
    await fs.mkdir(dirname(path), { recursive: true });
    await fs.writeFile(path, bytes);
    return path;
  }
}
