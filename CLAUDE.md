# abysshub-sdk

The official libraries for the Abyss API (`/v1`): **`abysshub`** for JavaScript and Python. This repo is **public** (MIT).

- **`js/`** is the npm package `abysshub`: TypeScript, shipped as ESM with types.
- **`python/`** is the PyPI package `abysshub`: Python, with plain dataclasses and `py.typed`.
- **`exchanges/`** holds the recorded exchanges. Each one is a JSON file of requests and responses, including chunks with leading spaces and cuts. A tiny fake server replays them. **Both libraries pass the same exchanges, with the same outcome.**
- **`contract/openapi.json`** is `/v1`'s contract, copied from the api. Every recorded body is validated against it. It is never edited here (see "The contract file").

The libraries are written by hand. The api's ADR-0042 (Amendments 2026-10-04 and 2026-10-05) decided them, and the parts a change here needs are quoted below, because this repo cannot read the api's.

## The `/v1` contract the libraries speak

- **Address:** `https://api.abysshub.com`. A key starting `abyss_sk_dev_` goes to `https://api.dev.abysshub.com` instead. `ABYSS_BASE_URL` (or the `baseURL` / `base_url` option) overrides both.
- **Auth:** `Authorization: Bearer <key>`. The key comes from `ABYSS_API_KEY`, or the `apiKey` / `api_key` option.
- **The press:** `POST /v1/widgets/{widget}/runs`, where `{widget}` is `widget_<id>` or an unlisted Widget's private token.
  - The JSON body is `{"input": {…}, "max_price"?: number, "wait"?: false}`. The header `Idempotency-Key` is optional and kept for 24 h.
  - **By default it holds.** It sends `200` and its headers at once (`Location: <base>/v1/runs/run_…`, `Request-Id`), then a space every 2 s, then the run JSON when the run ends. Read `status`, never the HTTP code, to learn how a run ended.
  - `"wait": false` answers `202` at once, with the run `queued`.
  - When the holds are full, it answers `202` at once.
  - After 1 h, it answers `200` with the run still `running`.
  - A deploy can cut a hold.
- **The read:** `GET /v1/runs/{id}` answers at once. With `?wait=true` it holds like the press.
- **A repeat with the same `Idempotency-Key` and body** answers the same run and holds again, with `Idempotent-Replayed: true`.
- **Uploads:** `POST /v1/widgets/{widget}/uploads` with `{"field", "filename", "size"?}` answers `{"id", "upload": {"url", "fields"}}`.
  - POST every `fields` entry, then the file as `file`, to `url` (S3).
  - Then put `id` in `input`. A file Field also takes an `https` URL string.
- **Other routes:**
  - `GET /v1/runs?limit=&starting_after=` answers `{data, has_more}`;
  - `GET /v1/widgets/{widget}` answers `{id, name, description, url, price, free_runs, input_schema}`;
  - `GET /v1/key`;
  - `GET /v1/openapi.json`.
- **The run object:** `{id, widget, status: queued|running|succeeded|failed, price, result, output_files: [{path, size, content_type, url}], error: {code, message}|null, created_at, started_at, ended_at}`. Each `url` is signed fresh on every read, and expires.
- **Errors:** `{"error": {"code", "message", "param"?, "doc_url", …extras}, "request_id"}`.

  | Status | Codes |
  |---|---|
  | 401 | `invalid_api_key` |
  | 404 | `not_found` |
  | 422 | `invalid_request`, `invalid_input`, `held_input_*`, `input_unreachable`, `idempotency_key_reused` |
  | 402 | `insufficient_funds` (+ `shortfall`) |
  | 400 | `spend_cap_reached`, `price_above_max` |
  | 409 | `idempotency_key_in_use` (+ `Retry-After`) |
  | 429 | `rate_limited` (+ `Retry-After`) |
  | 500 | `server_error` |

  A failed run's `error.code` is `widget_fault`, `platform_fault` or `budget_exceeded`.

## The library's own rules

- **The call:** `abyss.run(widget, input)` presses, holds and re-attaches, then returns a succeeded run. Under it there is one method per route: `runs.create / get / list`, `widgets.get`, `uploads.create` and `key()`.
- **Re-attaching:** a hold cut after its headers arrived, a `202`, and a `200` still `running` are all followed by `GET <Location>?wait=true` until the run ends. Re-attaching has no limit and is not a retry. 10 s to connect; 30 s of silence counts as a cut.
- **Retries:** at most 2 (`maxRetries` / `max_retries`), only for a drop before any headers, `429`, `409` (wait `Retry-After`) and `5xx` (short backoff). Every press carries one `Idempotency-Key`, a fresh UUID unless the caller sets it. Every other refusal raises at once.
- **Errors:** a refusal or a failed run raises one `AbyssError` carrying `code`, `message`, `param`, `doc_url` and `request_id`, plus `run` for a failed run. There is no class per status.
- **Timeouts:** none by default. An opt-in `timeout` (and `signal` in JS) stops the waiting, never the run, and raises `AbyssError` with the library-only code `timeout` and `.run`.
- **Files:** `file(path)` is the form the docs show; native files and bytes are accepted too, and a string passes through as an `https` URL or an upload id. The library uploads once and retries only the press. `run.save(dir)` saves every output file, and each file has `save()` and `read()`; an expired URL is refreshed once by re-reading the run.
- **The import shape:** the api's per-Widget code fixes it: `import Abyss, { file } from "abysshub"` in JS (`Abyss` is the default export, and the named `Abyss` is the same class) and `from abysshub import Abyss, file` in Python. Neither may break.
- **The naming rule:** returned data keeps `/v1`'s names in both languages. The library's own options follow each language (JS `maxPrice`, Python `max_price`). A Field's name is never converted.

## House rules

- **JS has no dependencies.** Not one runtime `dependency` in `js/package.json`; dev tools only. It runs on Node 20+, Bun and Deno, and in a browser `new Abyss()` throws.
- **Python has one dependency, `httpx`.** Python 3.10+, one sync client `Abyss` (`AsyncAbyss` is its own Slice). `python/pyproject.toml` declares a `dev` extra with the test tools.
- **Oldest supported versions first.** Code must run on Node 20 and Python 3.10. CI also runs newer versions, Bun and Deno.
- **The tests:** `npm test` in `js/` and `pytest` in `python/`. `.github/workflows/ci.yml` runs both on every pull request, on the oldest and the newest versions. A change to `exchanges/` keeps both languages green.
- **The packages started as placeholders that hold the published names.** Each one has a test of its dependency rule. Build on `js/package.json` and `python/pyproject.toml`: keep their `name`, their `version` of `0.0.0`, and `repository` (trusted publishing checks it).
- **This repo is public.** Its issues, pull requests and commits are visible to anyone. Never write a key, a secret, or another repo's code into them.

## The contract file

`contract/openapi.json` is a copy of the api's `resources/v1/openapi.json` on its `develop` branch. It is refreshed from the abyss workspace with `make sdk-contract`, then committed here. It is never edited by hand. The nightly live run fails when it differs from what dev serves at `/v1/openapi.json`. When a refresh turns the exchange validation red, the libraries need a Slice.

## Releases

- **`.github/workflows/release.yml` is the only workflow that publishes.** It runs `ci.yml` on the commit first and publishes only when the tests pass.
- **Every merge to `main` publishes a pre-release:** npm `abysshub@next` and a PyPI `.devN`, in the `next` environment, which deploys from `main` only. This is the dev track: dev walks install the library the way a caller would.
- **A stable version publishes only from a published GitHub Release tagged `vX.Y.Z`:** npm `latest` and a final PyPI version, in the `release` environment, which waits for a maintainer's approval.
- **The workflow computes every version.** A stable version is its tag. A pre-release is the patch after the newest `vX.Y.Z` tag on `main`, plus the number of commits since that tag: `0.1.1-dev.4` on npm, `0.1.1.dev4` on PyPI. The `0.0.0` in the package files is never bumped.
- **Publishing uses trusted publishing only.** Each registry trusts `release.yml` in the `next` and `release` environments, and nothing else. No token is stored anywhere.
- **Agents never publish.** They never run `npm publish` or `twine`, never create a release or a tag, never run `gh workflow run`, never change a package's name or version, and never edit `release.yml`. They change `ci.yml` only when their issue asks for it.

## Docs

The glossary is `CONTEXT.md` and the decisions are in `docs/adr/`, both created when there is something to write. A decision that shapes `/v1` itself belongs to the api's ADRs, not here.

## Git and issues

- The base branch is **`main`** (there is no `develop`). Branches and pull requests target it.
- Issues live in this repo: `gh issue … -R Abysshub/abysshub-sdk`. The triage labels are `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, plus `prod-cutover` for work that happens only at the prod cutover.

## Terminal output

Never pipe raw command output into context. Aim for 20 lines or fewer on success and 40 or fewer on failure.

```bash
<command> 2>&1 | grep -E "error|Error|FAIL|failed|passed|✓" | tail -20; echo "exit:$?"
```

For output that may run past about 50 lines (full test suites, installs), redirect it, then tail:

```bash
<command> > /tmp/cmd.log 2>&1 && echo OK || { echo "FAILED — last 30:"; tail -30 /tmp/cmd.log; }
```
