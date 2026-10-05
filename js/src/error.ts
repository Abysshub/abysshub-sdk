import type { Run } from "./types.js";

export interface AbyssErrorFields {
  code: string;
  message: string;
  status?: number | null;
  param?: string | null;
  doc_url?: string | null;
  request_id?: string | null;
  run?: Run | null;
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
  readonly run: Run | null;

  constructor(fields: AbyssErrorFields) {
    super(fields.message);
    this.name = "AbyssError";
    this.code = fields.code;
    this.status = fields.status ?? null;
    this.param = fields.param ?? null;
    this.doc_url = fields.doc_url ?? null;
    this.request_id = fields.request_id ?? null;
    this.run = fields.run ?? null;
  }
}
