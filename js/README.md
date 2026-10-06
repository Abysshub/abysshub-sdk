# abysshub

Pre-release: the Abyss API opens soon.

The official JavaScript library for the [Abyss](https://abysshub.com) API.

```js
import Abyss, { AbyssError } from "abysshub";

const abyss = new Abyss(); // reads ABYSS_API_KEY

try {
  const run = await abyss.run("widget_131", { amount: 250000 });
  console.log(run.result);
} catch (error) {
  if (error instanceof AbyssError) console.error(error.code, error.param, error.request_id, error.run);
  else throw error;
}
```

`Abyss` is the package's default export, the form each Widget's page shows. The named form, `import { Abyss } from "abysshub"`, works too and is the same class.

`run()` presses the Widget and waits for the run to end, however long it takes, then returns the succeeded run. A refusal or a failed run raises `AbyssError`.

It runs on Node 20+, Bun and Deno, with no dependencies. An API key is a server-side secret, so in a browser `new Abyss()` throws.

## The client

```js
const abyss = new Abyss({ apiKey, baseURL, maxRetries, timeout });
```

- **`apiKey`:** defaults to `ABYSS_API_KEY`. Without a key, `new Abyss()` raises `AbyssError` with `code: "invalid_api_key"`.
- **`baseURL`:** defaults to `ABYSS_BASE_URL`, else `https://api.abysshub.com`. A key starting `abyss_sk_dev_` goes to `https://api.dev.abysshub.com`.
- **`maxRetries`:** how many times a request is sent again (see [Retries](#retries)). Defaults to 2.
- **`timeout`:** the seconds every call waits at most, unless it sets its own (see [Timeouts](#timeouts)). None by default.

Every request sends `Authorization: Bearer <key>` and `User-Agent: abysshub-js/<version> (<runtime> <version>)`.

## Running a Widget

```js
const run = await abyss.run(widget, input, { maxPrice, idempotencyKey, timeout, signal });
```

- **`widget`** is `widget_<id>`, or an unlisted Widget's private token.
- **`input`** is the Widget's Fields by name (`GET /v1/widgets/{widget}` lists them as `input_schema`). A file Field takes a file (see [Files](#files)).
- **`maxPrice`:** the most the run may cost, in Byssium. A higher price is refused with `price_above_max`, and nothing is charged.
- **`idempotencyKey`:** each call presses with a fresh UUID `Idempotency-Key` unless you give one. Retries send the same one, so a run is never made or charged twice.

The press holds until the run ends. When the hold ends early (a deploy cuts it, the network goes down, the API's holds are all taken, or an hour passes), `run()` re-attaches with `GET <Location>?wait=true` until the run ends. Re-attaching has no limit and is not a retry. Connecting has 10 s, and 30 s of silence counts as a cut.

A **run** has `/v1`'s fields: `id`, `widget`, `status` (`queued`, `running`, `succeeded` or `failed`), `price`, `result`, `output_files`, `error`, `created_at`, `started_at` and `ended_at`.

## The routes

Under `run()` there is one method per route. Each takes `timeout` and `signal` in its last argument.

| Method | Route | Answers |
|---|---|---|
| `abyss.runs.create(widget, input, { maxPrice?, idempotencyKey? })` | `POST /v1/widgets/{widget}/runs` with `"wait": false` | the run, `queued`, at once |
| `abyss.runs.get(id, { wait? })` | `GET /v1/runs/{id}`, with `?wait=true` when `wait` | the run |
| `abyss.runs.list({ limit?, startingAfter? })` | `GET /v1/runs?limit=&starting_after=` | `{ data, has_more }`, newest first |
| `abyss.widgets.get(widget)` | `GET /v1/widgets/{widget}` | `{ id, name, description, url, price, free_runs, input_schema }` |
| `abyss.uploads.create(widget, { field, filename, size? })` | `POST /v1/widgets/{widget}/uploads` | `{ id, upload: { url, fields } }` |
| `abyss.key()` | `GET /v1/key` | `{ name, key, user, spend_cap, spent_this_month, created_at }` |

```js
const queued = await abyss.runs.create("widget_131", { amount: 250000 });
// … later, or in another process:
const run = await abyss.runs.get(queued.id, { wait: true });

let page = await abyss.runs.list({ limit: 100 });
while (page.has_more) page = await abyss.runs.list({ limit: 100, startingAfter: page.data.at(-1).id });
```

- **`runs.create()`** uploads the input's files like `run()`, then answers without waiting.
- **`runs.get()`** answers the run as it is, failed or not: only `run()` raises a failed run. With `wait`, it holds until the run ends, reading again when the hold is cut. A hold answers after an hour, or at once when the API's holds are all taken, so read again while `status` is `queued` or `running`.
- **`runs.list()`** answers each of `data` as a run, with `save()` and `output_files`.
- **`uploads.create()`** only asks for the grant. To upload by hand, POST every `fields` entry, then the file as `file`, to `url`, and put `id` in the input.

## Files

```js
import Abyss, { file } from "abysshub";

const run = await abyss.run("widget_1660", {
  report: file("report.pdf"),
  data: [file("jan.csv"), new File([csv], "feb.csv"), "https://example.com/sales/mar.csv"],
});
const paths = await run.save("output"); // ["output/charts/a.png", "output/output.json"]
```

- **`file(path)`** is a file on disk, read when it is uploaded. A file Field also takes a `Blob` or `File`, a `Buffer` or `Uint8Array`, or a stream (a web `ReadableStream`, or any async iterable such as `fs.createReadStream()`). `file(data, { filename })` names data. A file without a name uploads under its Field's name.
- **A string passes through** as an `https` URL or an upload id. A multi-file Field takes a list, which may mix all three kinds.
- **Before the press,** each file is uploaded with `POST /v1/widgets/{widget}/uploads`, then sent to storage, in parallel, and its id goes in the input. An upload refusal (`held_input_*`) raises before any press. A retried press reuses the ids; it never uploads again.
- **`await run.save(dir)`** writes every output file under `dir` at its `path`, making folders, and answers the paths it wrote.
- **Each of `run.output_files`** has `await f.save(path)` and `await f.read()`, which answers a `Uint8Array`. An expired URL is refreshed once, by reading the run again with `GET /v1/runs/{id}`.

## Errors

A refusal, a failed run, a timeout and a lost connection all raise one class, `AbyssError`. There is no class per status: branch on `code`.

| Field | |
|---|---|
| `code` | `/v1`'s error code, a failed run's `error.code`, or a library-only code below |
| `message` | what to do, for a person |
| `status` | the HTTP status of a refusal, else `null` |
| `param` | the Field, body key, query key or header at fault, else `null` |
| `doc_url` | the code on the API access page, else `null` |
| `request_id` | quote it to support, else `null` |
| `shortfall` | with `insufficient_funds`: how much Byssium the wallet is short, else `null` |
| `price` | with `price_above_max`: what the run costs now, else `null` |
| `run_id` | the id of the run the call started or read, once the press's `Location` or a run body named it, else `null` |
| `run` | the run, for a failed run or a timeout, else `null` |

- **Refusals:** `invalid_api_key` (401), `not_found` (404), `invalid_request`, `invalid_input`, `held_input_*`, `input_unreachable` and `idempotency_key_reused` (422), `insufficient_funds` (402), `spend_cap_reached` and `price_above_max` (400), `idempotency_key_in_use` (409), `rate_limited` (429), `server_error` (500).
- **A failed run:** `widget_fault`, `platform_fault` or `budget_exceeded`, with the run as `run`.
- **Library-only codes:** `timeout` (see [Timeouts](#timeouts)); `connection_error`, when the connection still drops before any answer after the retries, with the cause as `cause`; and `unexpected_response`, when an answer is not what the route sends.

## Retries

A request is sent again, at most `maxRetries` times (2 by default), only after:

- **a drop before any headers arrived:** a short backoff, then the same request, with the same `Idempotency-Key` for a press;
- **`429 rate_limited` and `409 idempotency_key_in_use`:** after the `Retry-After` seconds;
- **a `5xx`:** a short backoff (0.5 s, then 1 s).

When the last try fails too, it raises. Every other refusal raises at once.

**Re-attaching never counts as a retry.** A re-attach that drops, or meets a `429`, `409` or `5xx`, is tried again with no limit until the network is back, pausing 0.5 s and doubling to at most 10 s (or the `Retry-After` seconds). Only `timeout` and `signal` stop it.

## Timeouts

There is no timeout by default: `run()` waits as long as the run takes. `timeout` (seconds) and `signal` (an `AbortSignal`) stop the waiting, never the run.

```js
try {
  const run = await abyss.run("widget_131", input, { timeout: 60, signal: AbortSignal.timeout(90_000) });
} catch (error) {
  if (error instanceof AbyssError && error.code === "timeout" && error.run_id) {
    // The run goes on: wait for it again, without pressing (and paying) twice.
    const run = await abyss.runs.get(error.run_id, { wait: true });
  }
}
```

Either one raises `AbyssError` with `code: "timeout"`, `run`, the run as last seen or `null`, and `run_id`, the run's id. The press answers its `Location` at once, so `run_id` is set as soon as the press has answered, even while no run has been seen yet; it is `null` only when the waiting stopped before that. Nothing is sent after the waiting stops.

## Names

Returned data keeps `/v1`'s names: `output_files`, `has_more`, `request_id`. The library's own options are camelCase: `maxPrice`, `startingAfter`. A Field's name is never converted: `input` is sent as you write it.
