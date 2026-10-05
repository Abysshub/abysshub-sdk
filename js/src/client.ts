import { AbyssError } from "./error.js";
import { uploadFiles } from "./files.js";
import { request, type Answer } from "./http.js";
import { Run } from "./run.js";
import type { Input, Key, RunData, RunList, Upload, Widget } from "./types.js";
import { VERSION } from "./version.js";

const API = "https://api.abysshub.com";
const DEV_API = "https://api.dev.abysshub.com";
const DEV_KEY_PREFIX = "abyss_sk_dev_";

/** The pause between two re-attaches that both ended without the run's ending. */
const REATTACH_PAUSE_MS = 1_000;

/** The first pause before a retry after a drop or a 5xx; it doubles with each retry. */
const RETRY_PAUSE_MS = 500;

const BROWSER_REFUSAL = "An Abyss API key is a server-side secret. Call the API from your server.";

const USER_AGENT = `abysshub-js/${VERSION} (${runtime()})`;

export interface AbyssOptions {
  /** Defaults to `ABYSS_API_KEY`. */
  apiKey?: string;
  /** Defaults to `ABYSS_BASE_URL`, else the address the key belongs to. */
  baseURL?: string;
  /** How many times a request is sent again after a drop before any headers, a `429`, a `409` or a `5xx`. Defaults to 2. */
  maxRetries?: number;
  /** The seconds every call waits at most, unless it sets its own. None by default. */
  timeout?: number;
}

/** What every call takes. Stopping the waiting never stops the run. */
export interface CallOptions {
  /** The seconds to wait at most, then raise `AbyssError` with `code: "timeout"`. */
  timeout?: number;
  /** Aborting it stops the waiting, as `timeout` does. */
  signal?: AbortSignal;
}

export interface RunOptions extends CallOptions {
  /** The most this run may cost, in Byssium. */
  maxPrice?: number;
  /** Defaults to a fresh UUID for each call. */
  idempotencyKey?: string;
}

export interface GetRunOptions extends CallOptions {
  /** Holds until the run ends, as the press holds. */
  wait?: boolean;
}

export interface ListRunsOptions extends CallOptions {
  /** How many runs to answer, 1 to 100; the API's default is 20. */
  limit?: number;
  /** The `id` of the last run on the page you have. */
  startingAfter?: string;
}

/** What `uploads.create` asks for: the file Field, the file's name and its size in bytes. */
export interface UploadRequest {
  field: string;
  filename: string;
  size?: number;
}

/** `/v1`'s run routes, one method each. */
export interface Runs {
  /** Uploads the input's files and presses with `"wait": false`: answers the run at once, `queued`. */
  create(widget: string, input: Input, options?: RunOptions): Promise<Run>;
  /** Reads a run as it is, or with `wait` holds until it ends. A failed run is answered, not raised. */
  get(id: string, options?: GetRunOptions): Promise<Run>;
  /** Answers a page of runs, newest first. */
  list(options?: ListRunsOptions): Promise<RunList<Run>>;
}

export interface Widgets {
  /** Reads a Widget: its price, Free Runs and `input_schema`. */
  get(widget: string, options?: CallOptions): Promise<Widget>;
}

export interface Uploads {
  /** Asks for an upload's grant. `run()` and `runs.create()` upload files by themselves. */
  create(widget: string, upload: UploadRequest, options?: CallOptions): Promise<Upload>;
}

interface Reply {
  body: unknown;
  run: RunData | null;
  /** Whether the connection was cut, or went silent, after the headers. */
  cut: boolean;
  location: string | null;
  requestId: string | null;
}

type EndedReply = Reply & { run: RunData };

/** One call's waiting: the signal that stops it, and the run as last seen, for a timeout to carry. */
interface Call {
  signal: AbortSignal | null;
  seen: RunData | null;
}

export class Abyss {
  readonly baseURL: string;
  readonly maxRetries: number;
  readonly timeout: number | null;
  readonly runs: Runs;
  readonly widgets: Widgets;
  readonly uploads: Uploads;
  readonly #apiKey: string;

  constructor(options: AbyssOptions = {}) {
    if (inBrowser()) throw new Error(BROWSER_REFUSAL);
    const apiKey = options.apiKey ?? env("ABYSS_API_KEY");
    if (!apiKey) {
      throw new AbyssError({
        code: "invalid_api_key",
        message: "No Abyss API key: pass apiKey, or set ABYSS_API_KEY.",
      });
    }
    this.#apiKey = apiKey;
    const baseURL = options.baseURL ?? env("ABYSS_BASE_URL") ?? (apiKey.startsWith(DEV_KEY_PREFIX) ? DEV_API : API);
    this.baseURL = baseURL.replace(/\/+$/, "");
    this.maxRetries = options.maxRetries ?? 2;
    this.timeout = options.timeout ?? null;
    this.runs = {
      create: (widget, input, options = {}) =>
        this.#call(options, async (call) => {
          const press = await this.#press(call, widget, input, options, false);
          return this.#run(expect(press, isRun, "The press answered without a run."));
        }),
      get: (id, options = {}) =>
        this.#call(options, async (call) => this.#run(await this.#getRun(call, id, options.wait ?? false))),
      list: (options = {}) => this.#call(options, (call) => this.#listRuns(call, options)),
    };
    this.widgets = {
      get: (widget, options = {}) =>
        this.#call(options, (call) => this.#get(call, this.#widgetURL(widget), isWidget, "The Widget answered without an id.")),
    };
    this.uploads = {
      create: (widget, upload, options = {}) => this.#call(options, (call) => this.#grant(call, this.#widgetURL(widget), upload)),
    };
  }

  /**
   * Uploads the input's files, presses a Widget and waits for the run's ending,
   * re-attaching through `Location` whenever the hold ends early. Returns the succeeded
   * run; raises `AbyssError` on a refusal or a failed run.
   */
  run(widget: string, input: Input, options: RunOptions = {}): Promise<Run> {
    return this.#call(options, async (call) => {
      const press = await this.#press(call, widget, input, options, true);
      const reply = hasEnded(press) ? press : await this.#hold(call, this.#waitURL(press), hasEnded);
      const run = this.#run(reply.run);
      if (run.status === "failed") {
        throw new AbyssError({
          code: run.error?.code ?? "platform_fault",
          message: run.error?.message ?? "The run failed.",
          request_id: reply.requestId,
          run,
        });
      }
      return run;
    });
  }

  /** Answers the API Key making the call, with `GET /v1/key`. */
  key(options: CallOptions = {}): Promise<Key> {
    return this.#call(options, (call) => this.#get(call, `${this.baseURL}/v1/key`, isKey, "The key answered without a key."));
  }

  /**
   * Runs one call under its `timeout` and `signal`. When either stops the waiting, the
   * call raises `AbyssError` with `code: "timeout"` and the run as last seen.
   */
  async #call<T>(options: CallOptions, work: (call: Call) => Promise<T>): Promise<T> {
    const timeout = options.timeout ?? this.timeout;
    const stop = new AbortController();
    let message = "The signal stopped the waiting. The run goes on.";
    const abort = () => stop.abort();
    const timer =
      timeout === null
        ? undefined
        : setTimeout(() => {
            message = `Stopped waiting after ${timeout} s. The run goes on.`;
            abort();
          }, timeout * 1_000);
    if (options.signal?.aborted) abort();
    options.signal?.addEventListener("abort", abort, { once: true });
    const call: Call = { signal: stop.signal, seen: null };
    try {
      return await work(call);
    } catch (error) {
      if (!stop.signal.aborted) throw error;
      throw new AbyssError({ code: "timeout", message, run: call.seen && this.#run(call.seen) });
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
    }
  }

  /**
   * Uploads the input's files and sends the press, with `"wait": false` unless it holds.
   * Its retries send the same body and `Idempotency-Key`, so the uploads are never redone.
   */
  async #press(call: Call, widget: string, input: Input, options: RunOptions, hold: boolean): Promise<Reply> {
    const widgetURL = this.#widgetURL(widget);
    const body: Record<string, unknown> = {
      input: await uploadFiles(input, (field, filename, data) => this.#upload(call, widgetURL, field, filename, data)),
    };
    if (options.maxPrice !== undefined) body.max_price = options.maxPrice;
    if (!hold) body.wait = false;
    return this.#send(call, "POST", `${widgetURL}/runs`, {
      "Content-Type": "application/json",
      "Idempotency-Key": options.idempotencyKey ?? crypto.randomUUID(),
    }, JSON.stringify(body));
  }

  /** Asks for an upload with `POST /v1/widgets/{widget}/uploads`. */
  async #grant(call: Call, widgetURL: string, { field, filename, size }: UploadRequest): Promise<Upload> {
    // JSON.stringify leaves `size` out when it is undefined.
    const grant = await this.#send(
      call,
      "POST",
      `${widgetURL}/uploads`,
      { "Content-Type": "application/json" },
      JSON.stringify({ field, filename, size }),
    );
    return expect(grant, isUpload, "The upload answered without an id and a form.");
  }

  /** Asks for an upload, sends the file to storage and answers its id. */
  async #upload(call: Call, widgetURL: string, field: string, filename: string, data: Blob): Promise<string> {
    const grant = await this.#grant(call, widgetURL, { field, filename, size: data.size });
    const form = new FormData();
    for (const [name, value] of Object.entries(grant.upload.fields)) form.append(name, value);
    form.append("file", data, filename);
    const stored = await fetch(grant.upload.url, { method: "POST", body: form, signal: call.signal });
    await stored.body?.cancel();
    if (!stored.ok) {
      throw new AbyssError({
        code: "unexpected_response",
        message: `Storage answered ${stored.status} to the upload of ${filename}.`,
        status: stored.status,
        param: field,
      });
    }
    return grant.id;
  }

  /** Reads a run with `GET /v1/runs/{id}`, holding with `?wait=true`. A cut hold is read again. */
  async #getRun(call: Call, id: string, wait: boolean): Promise<RunData> {
    const url = new URL(`${this.baseURL}/v1/runs/${encodeURIComponent(id)}`);
    if (wait) url.searchParams.set("wait", "true");
    const reply = await this.#hold(call, url.href, (reply): reply is Reply => !reply.cut);
    return expect(reply, isRun, "The read answered without a run.");
  }

  async #listRuns(call: Call, options: ListRunsOptions): Promise<RunList<Run>> {
    const url = new URL(`${this.baseURL}/v1/runs`);
    if (options.limit !== undefined) url.searchParams.set("limit", String(options.limit));
    if (options.startingAfter !== undefined) url.searchParams.set("starting_after", options.startingAfter);
    const page = await this.#get(call, url.href, isRunList, "The run list answered without data.");
    return { data: page.data.map((data) => this.#run(data)), has_more: page.has_more };
  }

  /** Reads `url` once and answers its body, when it is what the route answers. */
  async #get<T>(call: Call, url: string, is: (value: unknown) => value is T, message: string): Promise<T> {
    return expect(await this.#send(call, "GET", url), is, message);
  }

  /** Reads `url` until `done`. Re-attaching has no limit and is not a retry. */
  async #hold<R extends Reply>(call: Call, url: string, done: (reply: Reply) => reply is R): Promise<R> {
    let reply = await this.#send(call, "GET", url);
    while (!done(reply)) {
      await sleep(REATTACH_PAUSE_MS, call.signal);
      reply = await this.#send(call, "GET", url);
    }
    return reply;
  }

  #run(data: RunData): Run {
    return new Run(data, () => this.#getRun({ signal: null, seen: null }, data.id, false));
  }

  #widgetURL(widget: string): string {
    return `${this.baseURL}/v1/widgets/${encodeURIComponent(widget)}`;
  }

  #waitURL(reply: Reply): string {
    const location = reply.location ?? (reply.run ? `/v1/runs/${reply.run.id}` : null);
    if (!location) {
      throw new AbyssError({
        code: "unexpected_response",
        message: "The press answered without a Location to read the run at.",
        request_id: reply.requestId,
      });
    }
    const url = new URL(location, `${this.baseURL}/`);
    url.searchParams.set("wait", "true");
    return url.href;
  }

  /**
   * Sends one request to `/v1`. A drop before any headers, a `429`, a `409` and a `5xx`
   * are sent again, at most `maxRetries` times; every other refusal raises at once.
   */
  async #send(call: Call, method: string, url: string, headers: Record<string, string> = {}, body?: string): Promise<Reply> {
    const init: RequestInit = {
      method,
      headers: { Authorization: `Bearer ${this.#apiKey}`, Accept: "application/json", "User-Agent": USER_AGENT, ...headers },
      signal: call.signal,
      ...(body === undefined ? {} : { body }),
    };
    for (let attempt = 0; ; attempt++) {
      let answer: Answer;
      try {
        answer = await request(url, init);
      } catch (error) {
        if (call.signal?.aborted) throw error;
        if (attempt >= this.maxRetries) {
          throw new AbyssError({
            code: "connection_error",
            message: "The connection dropped, or timed out, before the API answered.",
            cause: error,
          });
        }
        await sleep(backoff(attempt), call.signal);
        continue;
      }
      const requestId = answer.headers.get("request-id");
      const parsed = parse(answer.text);
      if (answer.status === 200 || answer.status === 202) {
        const run = isRun(parsed) ? parsed : null;
        if (run) call.seen = run;
        return { body: parsed, run, cut: answer.text === null, location: answer.headers.get("location"), requestId };
      }
      const pause = retryPause(answer, attempt);
      if (pause === null || attempt >= this.maxRetries) throw refusal(answer.status, parsed, requestId);
      await sleep(pause, call.signal);
    }
  }
}

/** How long to wait before sending a refused request again, or null when it is not retried. */
function retryPause(answer: Answer, attempt: number): number | null {
  if (answer.status === 429 || answer.status === 409) {
    const after = answer.headers.get("retry-after");
    const seconds = after === null ? Number.NaN : Number(after);
    return Number.isFinite(seconds) && seconds >= 0 ? seconds * 1_000 : backoff(attempt);
  }
  return answer.status >= 500 ? backoff(attempt) : null;
}

function backoff(attempt: number): number {
  return RETRY_PAUSE_MS * 2 ** attempt;
}

/** The reply's body when it is what the route answers, else `unexpected_response`. */
function expect<T>(reply: Reply, is: (value: unknown) => value is T, message: string): T {
  if (is(reply.body)) return reply.body;
  throw new AbyssError({ code: "unexpected_response", message, request_id: reply.requestId });
}

function refusal(status: number, body: unknown, requestId: string | null): AbyssError {
  const error = isObject(body) && isObject(body.error) ? body.error : null;
  if (!error || typeof error.code !== "string") {
    return new AbyssError({
      code: "unexpected_response",
      message: `The API answered ${status} without an error body.`,
      status,
      request_id: requestId,
    });
  }
  return new AbyssError({
    code: error.code,
    message: typeof error.message === "string" ? error.message : error.code,
    status,
    param: typeof error.param === "string" ? error.param : null,
    doc_url: typeof error.doc_url === "string" ? error.doc_url : null,
    request_id: isObject(body) && typeof body.request_id === "string" ? body.request_id : requestId,
  });
}

function parse(text: string | null): unknown {
  if (text === null) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRun(value: unknown): value is RunData {
  return isObject(value) && typeof value.id === "string" && typeof value.status === "string";
}

function isRunList(value: unknown): value is RunList {
  return isObject(value) && Array.isArray(value.data) && value.data.every(isRun) && typeof value.has_more === "boolean";
}

function isWidget(value: unknown): value is Widget {
  return isObject(value) && typeof value.id === "string";
}

function isKey(value: unknown): value is Key {
  return isObject(value) && typeof value.key === "string";
}

function isUpload(value: unknown): value is Upload {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    isObject(value.upload) &&
    typeof value.upload.url === "string" &&
    isObject(value.upload.fields)
  );
}

/** Whether the reply carries a run that has succeeded or failed. */
function hasEnded(reply: Reply): reply is EndedReply {
  return reply.run !== null && (reply.run.status === "succeeded" || reply.run.status === "failed");
}

function env(name: string): string | undefined {
  try {
    const { process } = globalThis as { process?: { env?: Record<string, string | undefined> } };
    return process?.env?.[name] || undefined;
  } catch {
    return undefined;
  }
}

/** Whether this runs in a browser, where an API key would be exposed. */
function inBrowser(): boolean {
  const scope = globalThis as { window?: unknown; document?: unknown };
  return scope.window !== undefined && scope.document !== undefined;
}

/** The runtime and its version, for the User-Agent. Bun and Deno also serve `process`, so they are asked first. */
function runtime(): string {
  const scope = globalThis as {
    Bun?: { version?: string };
    Deno?: { version?: { deno?: string } };
    process?: { versions?: { node?: string } };
  };
  if (scope.Bun?.version) return `bun ${scope.Bun.version}`;
  if (scope.Deno?.version?.deno) return `deno ${scope.Deno.version.deno}`;
  if (scope.process?.versions?.node) return `node ${scope.process.versions.node}`;
  return "unknown";
}

/** Waits `ms`, or rejects as soon as `signal` aborts. */
function sleep(ms: number, signal: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const stop = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", stop);
      resolve();
    }, ms);
    signal?.addEventListener("abort", stop, { once: true });
  });
}
