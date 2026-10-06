import type { Run } from "./run.js";

export interface AbyssErrorFields {
  code: string;
  message: string;
  status?: number | null;
  param?: string | null;
  doc_url?: string | null;
  request_id?: string | null;
  /** The id of the run the call started or read, once the call has learned it. */
  run_id?: string | null;
  /** With `insufficient_funds`: how much Byssium the wallet is short. */
  shortfall?: number | null;
  /** With `price_above_max`: what the run costs now. */
  price?: number | null;
  run?: Run | null;
  /** What a `connection_error` was caused by. */
  cause?: unknown;
}

/**
 * The one error the library raises: a refusal from `/v1`, or a run that failed.
 * Branch on `code`. A failed run carries the run as `run`.
 */
export class AbyssError extends Error {
  readonly code: string;
  /** The HTTP status of a refusal; null for a failed run. */
  readonly status: number | null;
  readonly param: string | null;
  readonly doc_url: string | null;
  readonly request_id: string | null;
  /**
   * The id of the run the call started or read, once the call has learned it from a
   * `Location` header or a run body; else null. A `timeout` carries it even when no run
   * body has arrived, so `runs.get(run_id, { wait: true })` finds the run again.
   */
  readonly run_id: string | null;
  /** With `insufficient_funds`: how much Byssium the wallet is short; else null. */
  readonly shortfall: number | null;
  /** With `price_above_max`: what the run costs now; else null. */
  readonly price: number | null;
  readonly run: Run | null;

  constructor(fields: AbyssErrorFields) {
    super(fields.message, fields.cause === undefined ? undefined : { cause: fields.cause });
    this.name = "AbyssError";
    this.code = fields.code;
    this.status = fields.status ?? null;
    this.param = fields.param ?? null;
    this.doc_url = fields.doc_url ?? null;
    this.request_id = fields.request_id ?? null;
    this.run_id = fields.run_id ?? null;
    this.shortfall = fields.shortfall ?? null;
    this.price = fields.price ?? null;
    this.run = fields.run ?? null;
  }
}
