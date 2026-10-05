import { AbyssError } from "./error.js";
import { uploadFiles } from "./files.js";
import { request } from "./http.js";
import { Run } from "./run.js";
import type { Input, RunData } from "./types.js";

const API = "https://api.abysshub.com";
const DEV_API = "https://api.dev.abysshub.com";
const DEV_KEY_PREFIX = "abyss_sk_dev_";

/** The pause between two re-attaches that both ended without the run's ending. */
const REATTACH_PAUSE_MS = 1_000;

/** The pause before pressing again after a drop before any headers. */
const RETRY_PAUSE_MS = 500;

export interface AbyssOptions {
  /** Defaults to `ABYSS_API_KEY`. */
  apiKey?: string;
  /** Defaults to `ABYSS_BASE_URL`, else the address the key belongs to. */
  baseURL?: string;
  maxRetries?: number;
}

export interface RunOptions {
  /** The most this run may cost, in Byssium. */
  maxPrice?: number;
  /** Defaults to a fresh UUID for each call. */
  idempotencyKey?: string;
}

interface Reply {
  body: unknown;
  run: RunData | null;
  location: string | null;
  requestId: string | null;
}

type EndedReply = Reply & { run: RunData };

export class Abyss {
  readonly baseURL: string;
  readonly maxRetries: number;
  readonly #apiKey: string;

  constructor(options: AbyssOptions = {}) {
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
  }

  /**
   * Uploads the input's files, presses a Widget and waits for the run's ending,
   * re-attaching through `Location` whenever the hold ends early. Returns the succeeded
   * run; raises `AbyssError` on a refusal or a failed run.
   */
  async run(widget: string, input: Input, options: RunOptions = {}): Promise<Run> {
    const widgetURL = `${this.baseURL}/v1/widgets/${encodeURIComponent(widget)}`;
    const body: Record<string, unknown> = {
      input: await uploadFiles(input, (field, filename, data) => this.#upload(widgetURL, field, filename, data)),
    };
    if (options.maxPrice !== undefined) body.max_price = options.maxPrice;
    const press = await this.#press(`${widgetURL}/runs`, {
      "Content-Type": "application/json",
      "Idempotency-Key": options.idempotencyKey ?? crypto.randomUUID(),
    }, JSON.stringify(body));
    const reply = hasEnded(press) ? press : await this.#reattach(press);
    const run = new Run(reply.run, () => this.#read(reply.run.id));
    if (run.status === "failed") {
      throw new AbyssError({
        code: run.error?.code ?? "platform_fault",
        message: run.error?.message ?? "The run failed.",
        request_id: reply.requestId,
        run,
      });
    }
    return run;
  }

  /**
   * Sends the press. A drop before any headers presses again, at most `maxRetries`
   * times, with the same body and `Idempotency-Key`, so the uploads are never redone.
   */
  async #press(url: string, headers: Record<string, string>, body: string): Promise<Reply> {
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.#send("POST", url, headers, body);
      } catch (error) {
        if (error instanceof AbyssError || attempt >= this.maxRetries) throw error;
        await sleep(RETRY_PAUSE_MS);
      }
    }
  }

  /** Asks for an upload with `POST /v1/widgets/{widget}/uploads`, sends the file to storage and answers its id. */
  async #upload(widgetURL: string, field: string, filename: string, data: Blob): Promise<string> {
    const grant = await this.#send(
      "POST",
      `${widgetURL}/uploads`,
      { "Content-Type": "application/json" },
      JSON.stringify({ field, filename, size: data.size }),
    );
    if (!isUpload(grant.body)) {
      throw new AbyssError({
        code: "unexpected_response",
        message: "The upload answered without an id and a form.",
        request_id: grant.requestId,
      });
    }
    const form = new FormData();
    for (const [name, value] of Object.entries(grant.body.upload.fields)) form.append(name, value);
    form.append("file", data, filename);
    const stored = await fetch(grant.body.upload.url, { method: "POST", body: form });
    await stored.body?.cancel();
    if (!stored.ok) {
      throw new AbyssError({
        code: "unexpected_response",
        message: `Storage answered ${stored.status} to the upload of ${filename}.`,
        status: stored.status,
        param: field,
      });
    }
    return grant.body.id;
  }

  /** Reads a run at once with `GET /v1/runs/{id}`. */
  async #read(id: string): Promise<RunData> {
    const reply = await this.#send("GET", `${this.baseURL}/v1/runs/${encodeURIComponent(id)}`);
    if (!reply.run) {
      throw new AbyssError({
        code: "unexpected_response",
        message: "The read answered without a run.",
        request_id: reply.requestId,
      });
    }
    return reply.run;
  }

  /** Reads the run with `GET <Location>?wait=true` until it ends. Re-attaching has no limit and is not a retry. */
  async #reattach(press: Reply): Promise<EndedReply> {
    const url = this.#waitURL(press);
    let reply = await this.#send("GET", url);
    while (!hasEnded(reply)) {
      await sleep(REATTACH_PAUSE_MS);
      reply = await this.#send("GET", url);
    }
    return reply;
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

  async #send(method: string, url: string, headers: Record<string, string> = {}, body?: string): Promise<Reply> {
    const answer = await request(url, {
      method,
      headers: { Authorization: `Bearer ${this.#apiKey}`, Accept: "application/json", ...headers },
      ...(body === undefined ? {} : { body }),
    });
    const requestId = answer.headers.get("request-id");
    const parsed = parse(answer.text);
    if (answer.status === 200 || answer.status === 202) {
      return { body: parsed, run: isRun(parsed) ? parsed : null, location: answer.headers.get("location"), requestId };
    }
    throw refusal(answer.status, parsed, requestId);
  }
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

function isUpload(value: unknown): value is { id: string; upload: { url: string; fields: Record<string, string> } } {
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
