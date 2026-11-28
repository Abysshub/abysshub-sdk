# abysshub-sdk

The official libraries for the Abyss API (`/v1`), written by hand: the npm package `abysshub` (`js/`, TypeScript, ESM with types), the PyPI package `abysshub` (`python/`, with the `abysshub` command), the n8n community node `n8n-nodes-abysshub` (`n8n/`), and the public agent skill `abyss-widget` (`skills/abyss-widget/`). **This repo is public (MIT):** never write a key, a secret or another repo's code into an issue, a pull request or a commit.

## Rules

- The base branch is `main`. Issues live here: `gh issue … -R Abysshub/abysshub-sdk`.
- Words: `CONTEXT.md` is the glossary. It holds only the words the sdk adds; a platform word is the api's, as `contract/openapi.json` uses it. Decisions: `docs/adr/`. A decision that shapes `/v1` itself belongs to the api's ADRs.
- `contract/openapi.json` is `/v1`'s contract, copied from the api's `develop`. Never edit it by hand: the workspace root refreshes it with `make sdk-contract`. When a refresh turns the exchange validation red, the libraries need a Slice.
- **Both libraries pass the same `exchanges/`, with the same outcome.** A change to `exchanges/` keeps JS, Python and n8n green. A recorded command (`call.command`) is the exception: the `abysshub` command and the routes that change a Widget are Python's alone (ADR-0001).
- **JS has no runtime dependency** and runs on Node 20+; in a browser `new Abyss()` throws. **Python has one, `httpx`,** and runs on 3.9+, with a sync `Abyss` and an async `AsyncAbyss` that share methods and exchanges. The n8n node has none, by n8n's verified-node rules. Each package has a test of its dependency rule.
- **Code runs on Node 20 and Python 3.9.** Python 3.9 is the `python3` macOS ships, so a caller's first try on a Mac runs on it. It rules out `match`, `X | Y` outside an annotation, and 3.10's library additions (`zip(strict=)`, `dataclass(slots=)`). Raising a floor is the maintainer's decision, released as a minor version.
- **The import shape never breaks:** `import Abyss, { file } from "abysshub"`, `const { Abyss, file } = require("abysshub")` (Node 20.19+ and 22.12+; there is no CommonJS build), and `from abysshub import Abyss, file`. The api's per-Widget code prints these.
- **Returned data keeps `/v1`'s names** in both languages. The library's own options follow each language (JS `maxPrice`, Python `max_price`). A Field's name is never converted.
- Keep each package's `name`, its `version` of `0.0.0` and its `repository`: `release.yml` computes every version, and trusted publishing checks `repository`.
- **Agents never publish:** no `npm publish`, `twine`, release, tag or `gh workflow run`, and no change under `.github/workflows/`. The loop's token has no `workflow` scope, so GitHub refuses the push and the Lane fails. An issue that needs a workflow change is `ready-for-human`, done in a session with the maintainer.

## The skill

`skills/abyss-widget/` teaches a coding agent to build a Widget or Port a tool. It ships in no package; `.claude-plugin/marketplace.json` makes the repo a plugin marketplace whose one plugin is this folder, and `npm test` in `js/` validates it.
- `WIDGET.md` quotes the platform's Widget facts from the api, which this repo cannot read: a platform change to them changes that file too.
- `scripts/check_abyss.py` calls the Python library, and `ABYSS.md` reads the `abysshub` command's stops by `code`. A change to the library's public surface, or to the command's codes or flags, keeps them working.

## Commands

- JS: `cd js && npm ci && npm test` (build, tests, knip). n8n: `cd n8n && npm ci && npm test` (build, tests, n8n's scanner, knip). Python: `cd python && pip install -e ".[dev]" && pytest` (tests, vulture, deptry, ruff's ERA001).
- The Merge Proof runs all three. CI runs them on Node 20 and 24 and Python 3.9 and 3.14.
- Dead code: today's findings sit in `js/dead-code.json`, `n8n/dead-code.json` and `python/vulture_whitelist.py`. Only a new finding fails, and a recorded finding that is gone fails until it leaves the record.

## Traps

- `timeout` is in seconds in both languages, and there is none by default, so `run()` may wait forever. It stops the waiting, never the run.
- `runs.create()` returns a failed run; `run()` raises `AbyssError` with `.run`.
- The HTTP and retry code exists three times (JS, Python, n8n), and the copies disagree on what counts as success. A fix in one usually belongs in all three.
- `publish` writes `abyss.json` several times mid-flow; a failed run leaves its Draft and Candidate there, and the next `publish` takes them up.
- `live/` is the nightly live run against dev (`.github/workflows/live.yml`). Its scripts are not tests: `npm test` and `pytest` never collect them, and a change to the public surface keeps them working. The probe Widget is `live/widget`; a change to it changes both scripts.
- Every merge to `main` publishes a pre-release (`next`, `.devN`); a stable version publishes only from a GitHub Release `vX.Y.Z`, after the maintainer's approval.

## Terminal output

Never put raw command output into context: at most 20 lines on success and 40 on failure.

```bash
<command> 2>&1 | grep -E "error|Error|FAIL|failed|passed|✓" | tail -20; echo "exit:$?"
```

For long output (whole suites, installs), redirect to a file and tail its last 30 lines.
