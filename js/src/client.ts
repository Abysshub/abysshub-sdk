import { AbyssError } from "./error.js";
import { request } from "./http.js";
import type { Input, Run } from "./types.js";

const API = "https://api.abysshub.com";
const DEV_API = "https://api.dev.abysshub.com";
const DEV_KEY_PREFIX = "abyss_sk_dev_";

/** The pause between two re-attaches that both ended without the run's ending. */
const REATTACH_PAUSE_MS = 1_000;

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
  run: Run | null;
  location: string | null;
  requestId: string | null;
}

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
   * Presses a Widget and waits for the run's ending, re-attaching through `Location`
   * whenever the hold ends early. Returns the succeeded run; raises `AbyssError` on a
   * refusal or a failed run.
   */
  async run(widget: string, input: Input, options: RunOptions = {}): Promise<Run> {
    const body: Record<string, unknown> = { input };
    if (options.maxPrice !== undefined) body.max_price = options.maxPrice;
    let reply = await this.#send("POST", `${this.baseURL}/v1/widgets/${encodeURIComponent(widget)}/runs`, {
      "Content-Type": "application/json",
      "Idempotency-Key": options.idempotencyKey ?? crypto.randomUUID(),
    }, JSON.stringify(body));
    let target: string | null = null;
    while (!reply.run || !isFinal(reply.run)) {
      if (target) await sleep(REATTACH_PAUSE_MS);
      else target = this.#waitURL(reply);
      reply = await this.#send("GET", target);
    }
    if (reply.run.status === "failed") {
      throw new AbyssError({
        code: reply.run.error?.code ?? "platform_fault",
        message: reply.run.error?.message ?? "The run failed.",
        request_id: reply.requestId,
        run: reply.run,
      });
    }
    return reply.run;
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
      return { run: isRun(parsed) ? parsed : null, location: answer.headers.get("location"), requestId };
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

function isRun(value: unknown): value is Run {
  return isObject(value) && typeof value.id === "string" && typeof value.status === "string";
}

function isFinal(run: Run): boolean {
  return run.status === "succeeded" || run.status === "failed";
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
