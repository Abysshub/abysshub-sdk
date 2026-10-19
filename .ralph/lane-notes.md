# Lane notes — abysshub-sdk

What a ralph Lane in this repo needs beyond `CLAUDE.md`, which quotes the `/v1` contract and the house rules because this sandbox cannot read the api repo (the workspace's root ADR-0015). The loop reads this file and `profile.json` from `origin/main` when it launches.

## Writing code here

- Read `contract/openapi.json` when your change touches a route, a field or an error code. Never edit it: if it is wrong or stale, that is a blocker.
- When the other language already does what the issue asks, read how it does it: both libraries behave the same on the same exchanges. A new behaviour gets a recorded exchange in `exchanges/` (shared by both languages) rather than a mock written for one language.
- The sandbox runs the **oldest supported versions**: Node 20 and Python 3.9 (a venv on `PATH`). Never install another Node or Python. Code that needs a newer runtime is a bug.
- Dependencies are **installed** when the Lane starts (Deps Sync): `js/node_modules` and the Python venv are ready — never run `npm ci`. If you add or change a dev dependency, run `npm install -D <pkg>` in `js/` or edit `python/pyproject.toml` and `pip install -e "./python[dev]"`, and commit the lockfile or manifest.

## Checks

The implementer and the reviewer each run:

- `npm test` in `js/` and `pytest` in `python/` — every language that exists must pass, and both must pass when you touch `exchanges/`. If your issue starts a language, create its test command under that name.
- Every recorded body must validate against `contract/openapi.json`.

## Review

- Re-attaching, retries and refusals are handled as the library's rules in `CLAUDE.md` say.
- Both languages behave the same on the same exchanges. A behaviour tested with a one-language mock instead of a recorded exchange is a gap.

## Resolving a conflict

- Two branches that both added a recorded exchange keep both files; a conflict in a shared exchange keeps both sides' cases.
