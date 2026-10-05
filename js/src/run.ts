import { AbyssError } from "./error.js";
import { nodeFS, nodePath } from "./node.js";
import type { RunData, RunError, RunFileData, RunStatus } from "./types.js";

/** Reads the run again with `GET /v1/runs/{id}`. */
export type Reread = () => Promise<RunData>;

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

  /** Downloads the file. An expired `url` is refreshed once, by reading the run again. */
  async read(): Promise<Uint8Array> {
    let response = await fetch(this.url);
    if (response.status === 403) {
      await response.body?.cancel();
      await this.#refresh();
      response = await fetch(this.url);
    }
    if (!response.ok) {
      await response.body?.cancel();
      throw new AbyssError({
        code: "unexpected_response",
        message: `The download of ${this.path} answered ${response.status}.`,
        status: response.status,
      });
    }
    return new Uint8Array(await response.arrayBuffer());
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
