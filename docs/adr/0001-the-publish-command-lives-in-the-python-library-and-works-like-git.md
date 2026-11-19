# The publish command lives in the Python library and works like git

**Status:** accepted 2026-11-20

A maker's coding agent could build a Widget with the `abyss-widget` skill, but the last step was a
person at the website who drags the folder, presses Test Run and fills the listing. The api now
lets an API Key with **Manage Widgets** do that step through `/v1` (the api's ADR-0068, decided on
2026-11-20). This repo cannot read the api's ADRs, so the parts a change here needs are quoted
below. The aim is a build before 2026-12-01.

## Decided

- **The command is `abysshub`, and it ships in the Python package only.** A maker runs it with
  `uvx abysshub …`, `pipx run abysshub …`, or `python -m abysshub …` after `pip install abysshub`.
  Each Widget maker has Python, because a Widget is Python and the skill's two scripts already run
  on it. Node is not certain on a maker's machine. The command adds no dependency: `httpx` stays the
  only one, and it runs on Python 3.9.
- **This is one exception to "both libraries pass the same exchanges".** The routes that change a
  Widget are spoken by the Python package alone until someone asks for them in JavaScript. Their
  recorded exchanges are replayed by `pytest` only. The JavaScript package and the n8n node do not
  change.
- **It has three verbs, and they work like git.**
  - `abysshub status <folder>` changes nothing. It shows the live Widget beside the folder: the
    version, each Listing Field that differs, where each Environment name comes from (the Widget or
    the account), and whether the Widget moved since the folder's last publish or pull.
  - `abysshub pull <folder>` writes the Widget's Listing Fields and thumbnail into the folder. It
    never touches code.
  - `abysshub publish <folder>` is the push. It prints the same comparison first. It then uploads the
    folder, makes the Test Run from the Test Inputs, waits, saves the Listing Fields and publishes.
- **A publish stops when the Widget moved.** If the Listing Fields or the code changed on the
  website since the folder's last publish or pull, `publish` stops before it uploads anything and
  names what moved. The maker pulls and publishes again, or `--force` makes the folder win.
- **The command asks nothing at a prompt.** An agent cannot answer one. It stops or it goes, it
  exits with a non-zero code when it stops, and each refusal carries the api's `code`. A failed Test
  Run prints the run's logs.
- **Two files in the folder say what to publish.**
  - The **Publish File**, `abyss.json`, holds the Listing Fields (title, tags, description,
    visibility, price, Free Runs, the thumbnail's path) and, after the first publish, which Widget
    the folder is and what that Widget was at the last publish or pull. The command never uploads
    it.
  - The **Test Inputs**, `test_inputs.json`, hold one value for each Field. A file Field names a
    file inside the folder. They are uploaded with the folder, as `interface.json` is.
- **A Widget starts Private unless the Publish File says public,** and a first publish needs a
  thumbnail.
- **The Junk list comes from the api.** The api sends it when a version is opened. The command
  leaves those entries out and names them. It keeps no copy of the list.
- **A root `.env` is sent as the Widget's Creator Environment, by the api's rules.** The command
  sends the names and values, and the api answers by name what it added, skipped and kept. The
  command prints that. `--use-env-file` replaces a value that the Widget already holds with the
  file's value. The command never sends a value that is an Abyss key, and it reads `ABYSS_API_KEY`
  from the environment, never from the folder's `.env`.
- **It ends with the link to the live Widget:** the page's address for a listed Widget, the
  Widget's Private Link for a Private one.
- **The skill uses it.** `abyss-widget` writes the two files and runs the command when the maker's
  key has Manage Widgets. Without such a key it keeps the website's steps.

## Considered options

- **The JavaScript package, run with `npx`.** Not now: a maker of a Python Widget has Python for
  sure and Node only perhaps. It can follow.
- **Both packages at once.** Rejected for the date: the same work twice before anyone has asked.
- **A script inside the skill.** Rejected: only an agent with the skill could publish, and a CI
  pipeline or a plain terminal could not.
- **Listing values as flags.** Rejected: an agent writes a file better than a long line, and a file
  gives the same result on a second run.
- **The folder always wins.** Rejected: a title changed on the website would be overwritten by an
  agent's next fix.
