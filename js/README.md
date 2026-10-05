# abysshub

The official JavaScript library for the [Abyss](https://abysshub.com) API.

Pre-release: the Abyss API opens soon.

```js
import { Abyss, AbyssError } from "abysshub";

const abyss = new Abyss(); // reads ABYSS_API_KEY

try {
  const run = await abyss.run("widget_131", { amount: 250000 });
  console.log(run.result);
} catch (error) {
  if (error instanceof AbyssError) console.error(error.code, error.param, error.request_id, error.run);
  else throw error;
}
```

`run()` presses the Widget and waits for the run to end, however long it takes, then returns the succeeded run. A refusal or a failed run raises `AbyssError`.

- **`new Abyss({ apiKey?, baseURL?, maxRetries? })`:** the key defaults to `ABYSS_API_KEY`. A key starting `abyss_sk_dev_` goes to `https://api.dev.abysshub.com`. `ABYSS_BASE_URL` or `baseURL` overrides the address.
- **`abyss.run(widget, input, { maxPrice?, idempotencyKey? })`:** each call presses with a fresh UUID `Idempotency-Key` unless you give one.
- **A run** has `/v1`'s fields: `id`, `widget`, `status`, `price`, `result`, `output_files`, `error`, `created_at`, `started_at` and `ended_at`.
- **A drop before any headers** presses again, at most `maxRetries` times, with the same body and `Idempotency-Key`.
- **Names:** returned data keeps the API's names (`output_files`, `request_id`). Options are camelCase. Field names are never converted.

## Files

```js
import { Abyss, file } from "abysshub";

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
