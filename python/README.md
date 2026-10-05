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

It runs on Python 3.10+, with one dependency, `httpx`.

## The client

```python
abyss = Abyss(api_key=None, base_url=None, max_retries=2)
```

- **`api_key`:** defaults to `ABYSS_API_KEY`. Without a key, `Abyss()` raises `AbyssError` with `code == "invalid_api_key"`.
- **`base_url`:** defaults to `ABYSS_BASE_URL`, else `https://api.abysshub.com`. A key starting `abyss_sk_dev_` goes to `https://api.dev.abysshub.com`.

`abyss.close()` closes its connections; `with Abyss() as abyss:` does it for you.

## Running a Widget

```python
run = abyss.run(widget, input, max_price=None, idempotency_key=None)
```

- **`widget`** is `widget_<id>`, or an unlisted Widget's private token.
- **`input`** is the Widget's Fields by name, as a `dict`.
- **`max_price`:** the most the run may cost, in Byssium. A higher price is refused with `price_above_max`, and nothing is charged.
- **`idempotency_key`:** each call presses with a fresh UUID `Idempotency-Key` unless you give one.

The press holds until the run ends. When the hold ends early (a deploy cuts it, the API's holds are all taken, or an hour passes), `run()` re-attaches with `GET <Location>?wait=true` until the run ends. Re-attaching has no limit and is not a retry. Connecting has 10 s, and 30 s of silence counts as a cut.

A **run** is a dataclass with `/v1`'s fields: `id`, `widget`, `status` (`queued`, `running`, `succeeded` or `failed`), `price`, `result` (the Widget's JSON, a `dict` when it wrote an object), `output_files`, `error`, `created_at`, `started_at` and `ended_at`.

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

A refusal or a failed run raises one `AbyssError`. Branch on `code`:

- **`code`, `message`, `param`, `doc_url`, `request_id`:** from `/v1`'s error body. A failed run's `code` is `widget_fault`, `platform_fault` or `budget_exceeded`.
- **`status`:** the HTTP status of a refusal; `None` for a failed run.
- **`run`:** the failed run; `None` for a refusal.

The library's own codes: `invalid_api_key` (no key), `connection_error` (the connection dropped before the API answered) and `unexpected_response` (an answer that is not `/v1`'s).
