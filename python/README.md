# abysshub

The official Python library for the [Abyss](https://abysshub.com) API.

Pre-release: the Abyss API opens soon.

```python
from abysshub import Abyss, AbyssError

abyss = Abyss()  # reads ABYSS_API_KEY

try:
    run = abyss.run("widget_131", {"amount": 250000})
    print(run.result)
except AbyssError as error:
    print(error.code, error.param, error.request_id, error.run)
```

`run()` presses the Widget and waits for the run to end, however long it takes, then returns the succeeded run. A refusal or a failed run raises `AbyssError`.

It runs on Python 3.10+, with one dependency, `httpx`. The client is synchronous; from async code, run it in a thread:

```python
run = await asyncio.to_thread(abyss.run, "widget_131", {"amount": 250000})
```

## The client

```python
abyss = Abyss(api_key=None, base_url=None, max_retries=2, timeout=None)
```

- **`api_key`:** defaults to `ABYSS_API_KEY`. Without a key, `Abyss()` raises `AbyssError` with `code == "invalid_api_key"`.
- **`base_url`:** defaults to `ABYSS_BASE_URL`, else `https://api.abysshub.com`. A key starting `abyss_sk_dev_` goes to `https://api.dev.abysshub.com`.
- **`max_retries`:** how many times a request is sent again (see [Retries](#retries)). Defaults to 2.
- **`timeout`:** the seconds every call waits at most, unless it sets its own (see [Timeouts](#timeouts)). None by default.

Every request sends `Authorization: Bearer <key>` and `User-Agent: abysshub-python/<version> (python <version>)`.

`abyss.close()` closes its connections; `with Abyss() as abyss:` does it for you.

## Running a Widget

```python
run = abyss.run(widget, input, max_price=None, idempotency_key=None, timeout=None)
```

- **`widget`** is `widget_<id>`, or an unlisted Widget's private token.
- **`input`** is the Widget's Fields by name, as a `dict` (`abyss.widgets.get(widget)` lists them as `input_schema`). A file Field takes a file (see [Files](#files)).
- **`max_price`:** the most the run may cost, in Byssium. A higher price is refused with `price_above_max`, and nothing is charged.
- **`idempotency_key`:** each call presses with a fresh UUID `Idempotency-Key` unless you give one. Retries send the same one, so a run is never made or charged twice.
- **`timeout`:** the seconds to wait at most (see [Timeouts](#timeouts)).

The press holds until the run ends. When the hold ends early (a deploy cuts it, the API's holds are all taken, or an hour passes), `run()` re-attaches with `GET <Location>?wait=true` until the run ends. Re-attaching has no limit and is not a retry. Connecting has 10 s, and 30 s of silence counts as a cut.

A **run** is a dataclass with `/v1`'s fields: `id`, `widget`, `status` (`queued`, `running`, `succeeded` or `failed`), `price`, `result` (the Widget's JSON, a `dict` when it wrote an object), `output_files`, `error`, `created_at`, `started_at` and `ended_at`.

## The routes

Under `run()` there is one method per route. Each also takes `timeout=` as a keyword.

| Method | Route | Returns |
|---|---|---|
| `abyss.runs.create(widget, input, max_price=None, idempotency_key=None)` | `POST /v1/widgets/{widget}/runs` with `"wait": false` | the `Run`, `queued`, at once |
| `abyss.runs.get(id, wait=False)` | `GET /v1/runs/{id}`, with `?wait=true` when `wait` | the `Run` |
| `abyss.runs.list(limit=None, starting_after=None)` | `GET /v1/runs?limit=&starting_after=` | a `RunList`: `data`, `has_more`, newest first |
| `abyss.widgets.get(widget)` | `GET /v1/widgets/{widget}` | a `Widget`: `id`, `name`, `description`, `url`, `price`, `free_runs`, `input_schema` |
| `abyss.uploads.create(widget, field, filename, size=None)` | `POST /v1/widgets/{widget}/uploads` | an `Upload`: `id`, `upload.url`, `upload.fields` |
| `abyss.key()` | `GET /v1/key` | a `Key`: `name`, `key`, `user`, `spend_cap`, `spent_this_month`, `created_at` |

Each is a dataclass with `/v1`'s fields; `free_runs` is a `FreeRuns` (`limit`, `remaining`) or `None`, and `input_schema` stays a `dict`.

```python
queued = abyss.runs.create("widget_131", {"amount": 250000})
# … later, or in another process:
run = abyss.runs.get(queued.id, wait=True)

page = abyss.runs.list(limit=100)
while page.has_more:
    page = abyss.runs.list(limit=100, starting_after=page.data[-1].id)
```

- **`runs.create()`** uploads the input's files like `run()`, then returns without waiting.
- **`runs.get()`** returns the run as it is, failed or not: only `run()` raises a failed run. With `wait=True`, it holds until the run ends, reading again when the hold is cut. A hold answers after an hour, or at once when the API's holds are all taken, so read again while `status` is `queued` or `running`.
- **`runs.list()`** returns each of `data` as a `Run`, with `save()` and `output_files`.
- **`uploads.create()`** only asks for the grant. To upload by hand, POST every `upload.fields` entry, then the file as `file`, to `upload.url`, and put `id` in the input.

## Files

```python
from abysshub import Abyss, file

run = abyss.run("widget_1660", {
    "report": file("report.pdf"),
    "data": [file("jan.csv"), file(csv_bytes, filename="feb.csv"), "https://example.com/sales/mar.csv"],
})
paths = run.save("output")  # [Path("output/charts/a.png"), Path("output/output.json")]
```

- **`file(path)`** is a file on disk, read when it is uploaded. A file Field also takes a `Path`, an open file (`open("report.pdf", "rb")`) or `bytes`. `file(data, filename=...)` names data. A file without a name uploads under its Field's name.
- **A string passes through** as an `https` URL or an upload id. A multi-file Field takes a list, which may mix all three kinds.
- **Before the press,** each file is uploaded with `POST /v1/widgets/{widget}/uploads`, then sent to storage, in parallel, and its id goes in the input. An upload refusal (`held_input_*`) raises before any press. A press that drops before any headers is sent again with the same ids; it never uploads again.
- **`run.save(dir)`** writes every output file under `dir` at its `path`, making folders, and returns the paths it wrote.
- **Each of `run.output_files`** has `f.save(path)` and `f.read()`, which returns `bytes`. An expired URL is refreshed once, by reading the run again with `GET /v1/runs/{id}`.

## Errors

A refusal, a failed run, a timeout and a lost connection all raise one class, `AbyssError`. There is no class per status: branch on `code`.

| Field | |
|---|---|
| `code` | `/v1`'s error code, a failed run's `error.code`, or a library-only code below |
| `message` | what to do, for a person |
| `status` | the HTTP status of a refusal, else `None` |
| `param` | the Field, body key, query key or header at fault, else `None` |
| `doc_url` | the code on the API access page, else `None` |
| `request_id` | quote it to support, else `None` |
| `run` | the run, for a failed run or a timeout, else `None` |

- **Refusals:** `invalid_api_key` (401), `not_found` (404), `invalid_request`, `invalid_input`, `held_input_*`, `input_unreachable` and `idempotency_key_reused` (422), `insufficient_funds` (402), `spend_cap_reached` and `price_above_max` (400), `idempotency_key_in_use` (409), `rate_limited` (429), `server_error` (500).
- **A failed run:** `widget_fault`, `platform_fault` or `budget_exceeded`, with the run as `run`.
- **Library-only codes:** `timeout` (see [Timeouts](#timeouts)); `connection_error`, when the connection still drops before any answer after the retries, with the cause as `__cause__`; and `unexpected_response`, when an answer is not what the route sends.

## Retries

A request is sent again, at most `max_retries` times (2 by default), only after:

- **a drop before any headers arrived:** a short backoff, then the same request, with the same `Idempotency-Key` for a press;
- **`429 rate_limited` and `409 idempotency_key_in_use`:** after the `Retry-After` seconds;
- **a `5xx`:** a short backoff (0.5 s, then 1 s).

When the last try fails too, it raises. Every other refusal raises at once, and re-attaching never counts as a retry.

## Timeouts

There is no timeout by default: `run()` waits as long as the run takes. `timeout` (seconds), on the client or on a call, stops the waiting, never the run.

```python
try:
    run = abyss.run("widget_131", input, timeout=60)
except AbyssError as error:
    if error.code == "timeout":
        ...  # The run goes on. error.run is the run as last seen, or None when none was seen yet.
```

It raises `AbyssError` with `code == "timeout"` and `run`, the run as last seen. During the press's first hold the run has not been seen yet, so `run` is `None`; to keep its `id` whatever happens, press with `runs.create()` and wait with `runs.get(id, wait=True, timeout=...)`.

## Names

Returned data keeps `/v1`'s names: `output_files`, `has_more`, `request_id`. The library's own options are snake_case: `max_price`, `starting_after`. A Field's name is never converted: `input` is sent as you write it.
