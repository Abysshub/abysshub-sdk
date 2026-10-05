/** A run's place: `succeeded` and `failed` are final. */
export type RunStatus = "queued" | "running" | "succeeded" | "failed";

/** Why a run failed: `widget_fault`, `platform_fault` or `budget_exceeded`. */
export interface RunError {
  code: string;
  message: string;
}

/** One file a run wrote, as `/v1` sends it. */
export interface RunFileData {
  path: string;
  size: number;
  content_type: string;
  url: string;
}

/** A run, as `/v1` sends it. */
export interface RunData {
  id: string;
  widget: string;
  status: RunStatus;
  price: number;
  result: unknown;
  output_files: RunFileData[];
  error: RunError | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
}

/** A Widget's input: its Fields by name, never converted. */
export type Input = Record<string, unknown>;
