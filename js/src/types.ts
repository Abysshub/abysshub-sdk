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

/** A page of runs, newest first, as `GET /v1/runs` sends it. */
export interface RunList<R = RunData> {
  data: R[];
  /** Whether a page `starting_after` the last run here would find more. */
  has_more: boolean;
}

/** A Widget, as the caller about to press it sees it. */
export interface Widget {
  id: string;
  name: string | null;
  description: string | null;
  url: string;
  /** The one price a run costs, Call Price included. */
  price: number;
  /** The caller's Free Runs on this Widget; null for their own Widget and for a free one. */
  free_runs: { limit: number; remaining: number } | null;
  /** The JSON Schema the input must match. */
  input_schema: Record<string, unknown>;
}

/** An upload's grant: its `id` goes in the input once the file is in storage. */
export interface Upload {
  id: string;
  /** POST every `fields` entry, then the file as `file`, to `url`. */
  upload: { url: string; fields: Record<string, string> };
}

/** The API Key making the call, as `GET /v1/key` sends it. Never its secret. */
export interface Key {
  name: string;
  /** The key's display form: its prefix and last four characters. */
  key: string;
  user: { id: number; name: string };
  spend_cap: number | null;
  spent_this_month: number;
  created_at: string;
}
