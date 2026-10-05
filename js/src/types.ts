/** A run's place: `succeeded` and `failed` are final. */
export type RunStatus = "queued" | "running" | "succeeded" | "failed";

/** One file a run wrote. Its `url` is signed fresh on every read, and expires. */
export interface RunFile {
  path: string;
  size: number;
  content_type: string;
  url: string;
}

/** Why a run failed: `widget_fault`, `platform_fault` or `budget_exceeded`. */
export interface RunError {
  code: string;
  message: string;
}

/** A run, with `/v1`'s names. */
export interface Run {
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
}

/** A Widget's input: its Fields by name, never converted. */
export type Input = Record<string, unknown>;
