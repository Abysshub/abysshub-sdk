# Porting a tool to Abyss

A **Port** is a Widget you build from a tool the Creator already has somewhere else: an n8n flow, a Python script, a notebook, a Streamlit or Gradio app. It is checked against **Cases**, recorded uses of the original, and is done when its **Check** passes: the Port works and makes sense on those Cases. A Check never claims that the Port equals the original, so neither do you.

Work through the steps in order. Two of them stop for the Creator: the Done List (step 3), before any Widget code, and the local Check (step 7), before anything goes to Abyss. A message may carry the next step's request along with a gate (the upload steps with step 7's results), so the Creator answers once.

## The folders

```
<the original>/     the tool as the Creator has it; read it, never change it
<widget>/           the Widget, the folder the Creator uploads (WIDGET.md)
port/               everything else, never uploaded
  DONE-LIST.md      what this Port must do, confirmed by the Creator
  cases/<case>/     case.json, its input files, and original/: what the original produced
  original-run/     a copy of the original, its own virtualenv and versions.txt, when you run it to record Cases
  runs/             what each run of the Port produced: runs/local/<case>/, runs/abyss/<case>/
  CHECK.md          each Case's verdict
  .env              ABYSS_API_KEY, for the Abyss step only
  .venv/            the Widget's Python, for the local runs
  .venv-check/      the abysshub library, for the Abyss step
```

`<widget>/` and `port/` sit side by side, so a Case's files, which may be a client's real data, never enter the upload. When the project is under version control, add `port/` and `.env` to its `.gitignore`. `<this skill>` in the commands below is the folder holding SKILL.md.

## 1. Fit

Read the original end to end, then decide whether it ports. **Only a tool shaped like a function ports: one run takes inputs, does its work, ends, and hands back a Result and files.**

- The trigger in front of a function is the caller's, not the tool's. A webhook, a form, a "when a file lands in Drive" or a schedule that hands one item to a function: port the function, and say that whatever fired it now calls the Widget instead (through the API, or the Abyss node in n8n). A loop over many items ports as one run per item, or as one run over a batch the caller uploads; a Widget may take both (WIDGET.md, "A Widget that takes either a few values or a file of them").
- Decline, with the reason, a tool whose work *is* the waiting: a bot, a sync, a monitor, a long-running server, a web app with accounts, and anything that needs a person to sign in interactively on every run (see step 5 for a way around that one).
- Python is the only runtime. A JavaScript Code node or an n8n expression is rewritten in Python; an n8n node that calls a service becomes that service's HTTP API or its Python library.
- A Widget bundles the original's code and files, so its licence must allow that; carry its `LICENSE` into `<widget>/`.
- For a closed tool the Creator owns and has no source for, they may bring a reverse-engineering agent such as REA to recover how it behaves. Nothing here needs it.

**Done when** you can say in one sentence what one run takes and what it hands back, or you have declined and said why.

## 2. Cases

A Case is one recorded use of the original: the inputs it was given, and what it produced. Ask the Creator for a few ordinary ones (three to five, covering the shapes of input they really get) and at least one that should fail cleanly (the wrong kind of file, a missing column). Then add your own where theirs leave a gap, so that every kind of answer the tool gives (each label it can return, each way it fails) has a Case; say "made up" in its Done List row, for the Creator to accept. A sample that ships with the tool counts as a Case.

Where the original's outputs come from:

- **Records of real uses** are best: n8n's execution history, the files a script read and wrote, a notebook's saved outputs.
- **Without records, run the original** on the Case's inputs, in `port/original-run/` with its own virtualenv, when it can run here without sending anything (step 4). Keep that virtualenv's `pip freeze` as `port/original-run/versions.txt`, since these are the versions the Cases were recorded on. Run the original itself, never your reading of it:
  - a script or a notebook: run it on a copy, with the Case's files in place (`jupyter nbconvert --to notebook --execute` for a notebook);
  - a Streamlit app: `streamlit.testing.v1.AppTest.from_file("app.py")`, set its inputs, click its button, read what it shows;
  - a Gradio app: call the function the interface wraps, or the app through `gradio_client` while it runs locally.
- **When the original cannot run here**, work out what it would produce from its logic and the input itself (the invoice's printed total is the total), and write `original/EXPECTED.md` saying how. Where an input reads two ways (is 12/10/2026 October or December?), write the reading you expect and ask. The Creator confirms these with the Done List.

Store each Case as `port/cases/<case>/case.json`:

```json
{
  "input": {
    "invoice": {"file": "files/northwind-0142.pdf"},
    "currency": "EUR",
    "sections": ["summary", "totals"],
    "due": "2026-10-30"
  },
  "needs": ["ANTHROPIC_API_KEY"],
  "abyss": true
}
```

- Each key of `input` is a Field's name; use the names you will propose in the Done List, and rename them if the Creator changes them. A file Field's value is `{"file": "<path inside the case folder>"}`, or a list of them for a multi-file Field; a date is `YYYY-MM-DD`; a number is a JSON number.
- `needs` lists the secrets the run needs (step 5). Leave it out when there are none.
- `"abyss": true` marks a Case the Creator agrees may run on Abyss. Leave it out for real client data, which stays on this machine.
- `original/` holds what the original produced: its files, `result.json` when it answered with JSON, `log.txt` with what it printed (a traceback, for a Case that crashed it), and `EXPECTED.md` when the outputs were worked out rather than recorded.

A model saved with `pickle` or `joblib` loads only with the library version that saved it. Read that version without running the file: `python3 -m pickletools model.pkl | grep -A1 _sklearn_version` (for scikit-learn; `numpy._core` in the listing means NumPy 2). Never unpickle a file you have not read this way.

**Done when** every Case has its input files and its original outputs, recorded or expected and marked so.

## 3. The Done List

Write `port/DONE-LIST.md` for this one tool. Before you write it, look for what Abyss forces that the original never had to decide:

- a run of the original that succeeds with no output, or crashes: on Abyss an empty `output/` fails the run, so say what the Port does instead;
- the largest input the Creator expects, against the limits: the Result's 256 KB, 30 minutes, the file sizes;
- an odd behaviour, or a fault, of the original: the Port keeps it (step 6), and the Creator hears about it now.

```markdown
# Done List: <tool name>

## What one run does
<one sentence: takes …, hands back …>

## Mapping
| The original's | The Widget's |
|---|---|
| <an input: a webhook's file, an argparse option, a widget in the app> | Field `<name>` (<type>, <its limits>) |
| <a set-up value: a model name, a URL, a threshold> | a constant in `run.py` / an optional Field / a variable in Creator Environment |
| <an output: a response body, a written file, a chart> | Result key `<key>` / file `output/<name>` |

## Kept as the original does it
<every odd behaviour or fault of the original that the Port keeps, so nobody mistakes it for the Port's; or "nothing">

## Sends
<every message, upload or write to another system the original makes, and what the Port does instead; or "none">

## Secrets
<every key or password the Port needs, by its variable name, and what it is for; or "none">

## Cases
| Case | What it is | Runs on | Must hold | May vary |
|---|---|---|---|---|
| <name> | <an ordinary invoice, EUR, two lines> | local (Abyss if the Creator agrees) | <vendor, number, date and total match the invoice; output/bill.json is valid JSON> | <wording, key order, the model's phrasing> |
| <name> | <a PDF that is not an invoice> | local (Abyss if the Creator agrees) | <the run fails and makes no bill; locally, its log says why in one sentence> | <the sentence> |
```

- **Must hold** is what makes the output correct for this tool: totals, the fields that must be there, the files and their types, a row count. **May vary** is what can differ without being wrong: wording, order, formatting, an AI model's phrasing, timestamps. These are judgments about this tool; there is no rule that fits every tool, and exact matching is never one of them.
- The mapping follows these rules:
  - **A flat value becomes the matching Field**: text, a number, a choice, a date, a file.
  - **Nested data**, such as a webhook's JSON body, becomes a JSON file Field (`"mimes": ["json"]`), or a `text-area` when it is small.
  - **A set-up value** that is the same on every run stays a constant in `run.py`; one a caller may want to change becomes an optional Field; a private one is a secret.
  - **The original's outputs become the Result plus files**: what a program would read goes in the Result; documents, images and tables go in `output/`.

Then show the Creator the whole text, and in the same message ask which Cases may run on Abyss (each one's run stays in their account, since the API cannot delete it; propose none yourself, since you cannot tell their real data from test data) and which secrets they will supply (step 5). Wait for them to confirm or correct it. **No Widget code is written before they confirm.**

**Done when** the Creator has confirmed the Done List and said which Cases may go to Abyss, and each `case.json` says so.

## 4. Sends

By default a Port **returns what the original would have sent**, and the caller does the sending: the email's subject and body in the Result, the CRM row or the accounting entry as a file, the Slack message as text. The Port keeps the original's logic up to the moment of sending, and hands back exactly what it would have sent.

- **A send whose values come from another system's answer** (the bill needs the vendor's id, which a lookup or a create returns): leave those values empty in what you return, and write the rule that fills them.
- **Reading from another system to decide something** (does this vendor exist?) is not a send, but it needs that system's secrets. When it is not the point of the tool, return the request the original would have made, as it built it and without credentials, with the rule that uses its answer, and say so in the Done List.
- **A call that does the work itself** (a hosted model reading the invoice, an OCR service) is not a send: the Port makes it. List it under Sends anyway, so the Creator knows where their data goes.
- **Only when sending is the whole point of the tool** (it exists to post the message) does the Widget send. Then a Case that would reach a real third party runs only against a test account the Creator supplies, and only after they say yes for that Case. When the Creator's own words name the write ("it creates the bill in our Odoo"), offer them both ways in the Done List.

## 5. Secrets

List every secret the Port needs in the Done List, by the variable name the code reads, and in each Case's `needs`. The Creator writes them into `<widget>/.env`, one `NAME=value` per line, for the local runs; the uploader leaves that file out and copies its variables into Creator Environment for the runs on Abyss. Ask for them once the Done List is confirmed, and check before step 7 that `<widget>/.env` names each one: `grep -o '^[A-Za-z_][A-Za-z0-9_]*=' <widget>/.env`.

- Never read, print or invent a secret's value, and never write one into code, a Case, a log or the Done List.
- A Case that needs a secret the Creator has not supplied is **not run: needs `<NAME>`**, never failed; `run_local.py` reports it so from `needs`.
- A tool that needs an interactive OAuth sign-in on every run is declined, unless a long-lived token or a service account can replace the sign-in. Then that token is a secret like any other.

## 6. Build the Widget

Write `<widget>/` by WIDGET.md: `run.py`, `requirements.txt` and `interface.json` from the Done List's mapping. Make the Widget's own Python, at the version Abyss runs (3.12) when this machine has it, install what `run.py` imports at the versions the original used, then pin and check everything it holds:

```bash
python3.12 -m venv port/.venv        # or the newest python3 available
port/.venv/bin/pip install <each package>==<the original's version>
port/.venv/bin/pip freeze > <widget>/requirements.txt
```

and run `pip-audit` on it (WIDGET.md, "Dependencies").

- Keep the original's logic, and change only what Abyss needs: inputs read from the environment, outputs written under `output/`, secrets read from the environment, fixed paths and hard-coded file names replaced by the Fields. Running the same steps over many rows at once is keeping the logic, when the Cases show the same answers.
- Port the tool's prompts, formulas, thresholds and rules word for word. An improvement belongs to a later version, after the Check passes. Keep the original's error messages too; you may add one sentence saying what to fix.
- **JavaScript keeps its behaviour, not just its steps.** A Code node relies on JavaScript's truthiness (`0`, `""` and `NaN` are false), `parseFloat` (`parseFloat("1,742.16")` is `1`), `JSON.stringify` (`NaN` becomes `null`) and `+` joining strings. Write them as small helpers and test them on edge values.
- **A change the Creator asks for after confirming** (a cheaper model, a fix to the original) is theirs: record it in the Done List as their correction, mark it in the code with a comment, and run every Case again. A different model can change the shape of an answer, not just its wording.

**Done when** `run.py`, `requirements.txt` and `interface.json` exist, `interface.json` names every Field in the Done List, and `pip-audit` passes the pins, or each pin it flags is kept for a reason WIDGET.md allows.

## 7. The Check, on this machine

Run every Case with the Widget's Python from step 6:

```bash
python3 <this skill>/scripts/run_local.py <widget> port/cases/*
```

`run_local.py` runs each Case the way Abyss would and writes `port/runs/local/<case>/`: `run.json` (status, error, Result, files), `log.txt` and `output/`. Then judge every Case against the Done List, reading its outputs next to `original/`:

- **passed**: the run ended without a fault (for the Case that should fail, it failed with a clear reason), every output the Done List expects came out, and the content answers the same question the original's output did. The same invoice gives the same totals and vendor; the wording may differ.
- **failed**: any of those is not true. Say which, in one line.
- **not run**: a secret it needs is missing, or the Creator kept it from running (a real send without a test account).

Judge each Case's line, never the script's exit code: it exits 1 whenever any run failed, the Case meant to fail included. For a document, compare its extracted text with the original's; open an image and look. Their bytes differ by timestamps and ids.

A behaviour worth checking that no Case covers (a row with a bad value, an empty file) becomes a Case, never an untracked try: add it to the Done List's Cases, and show it to the Creator with the results below.

When the only fix for a failure would change the original's logic, not just how it runs on Abyss, it is the Creator's call: show them the failing run, and fix it only once they agree.

Write the verdicts into `port/CHECK.md`: one row per Case, with where it ran, the verdict and one line of why. Fix the Widget and run again until every Case that can run has passed. Then show the Creator the failures you fixed along the way, if any, and two or three passes with their outputs beside the original's, and ask whether they agree.

**Done when** every Case is passed or not run (with its reason), and the Creator has read the failures and the sample of passes and agreed.

## 8. The Check, on Abyss

The Check runs once more on Abyss, so it covers the build, the runtime and the upload. Follow ABYSS.md: the Creator puts the Widget on Abyss privately and gives you its address and an API key; you run the Cases marked `"abyss": true`:

```bash
python3 -m venv port/.venv-check && port/.venv-check/bin/pip install abysshub
port/.venv-check/bin/python <this skill>/scripts/check_abyss.py <the Widget's address> port/cases/*
```

It writes `port/runs/abyss/<case>/` the same way, prints the Widget's private link, and prints the ids of the runs it made. Judge those runs as in step 7, and add them to `CHECK.md` as rows of their own. A run made through the API carries no log, so a Case that should fail passes on Abyss when it failed with `widget_fault` and made none of its outputs; its sentence was judged locally. When `check_abyss.py` says the Abyss step isn't available yet, write that into `CHECK.md` and end the Check with the local runs.

**Done when** every `"abyss": true` Case has a verdict from its run on Abyss, or `CHECK.md` says the Abyss step wasn't available.

## 9. Hand it over

Tell the Creator, in this order:

1. What the Widget does, in one sentence, and its Fields.
2. The Check: how many Cases passed, failed or were not run, here and on Abyss, with `CHECK.md`'s path. Word the claim as **"it works and makes sense on these Cases"**, never as "identical to", "equivalent to" or "proven".
3. How others reach it. Only the Creator can open a private Widget by its page, so they share its private link (`check_abyss.py` prints it), which anyone holding it may open and run, or they make it public.
4. The ids of the runs made on Abyss. The API cannot delete a run, so they stay in the Creator's account; that is why only Cases they agreed to sent anything there.
5. What is left to them: who runs it now (where a person ran the original by hand, that person fills the Widget's form; a program calls it through the API, and the Widget page's **API** panel shows the code), what fired the original (the trigger, the schedule) and now calls the Widget, every send the Port handed back instead of making, every pin you changed, and what the Done List kept as the original does it, as candidates for a next version.
