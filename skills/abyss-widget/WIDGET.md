# What a Widget is

The facts a Widget must satisfy, as Abyss runs it. Consult this while you write `interface.json` and `run.py`, and again whenever a run behaves differently on Abyss than on the Creator's machine.

- [The project](#the-project)
- [The Fields: `interface.json`](#the-fields-interfacejson)
- [How inputs reach `run.py`](#how-inputs-reach-runpy)
- [Outputs and the Result](#outputs-and-the-result)
- [Secrets: Creator Environment](#secrets-creator-environment)
- [Limits](#limits)
- [How a run ends](#how-a-run-ends)
- [A complete `run.py`](#a-complete-runpy)

## The project

A Widget is a folder of Python, uploaded as it is:

- **`run.py`** at the root. Abyss runs `python3 run.py` from the folder's root.
- **`requirements.txt`** at the root, even when it is empty. It is installed once with `pip install -r requirements.txt` when the Widget is built, never during a run (see [Dependencies](#dependencies)).
- **`requirements.system`**, optional: apt package names, separated by spaces or newlines, installed with `apt-get install` at build time. Write only names in it; a comment breaks the build.
- **`interface.json`**, optional but always worth writing: the Fields, imported by the create wizard (see below).
- **Any other files** the code needs: templates, models, fonts, small data. The whole folder may be up to 512 MiB.

The runtime is **Ubuntu 24.04 with Python 3.12**, in a virtualenv. Python is the only runtime: a tool written in another language ports by rewriting its logic in Python, or by calling a binary that apt installs.

### Dependencies

- **Pin everything the Widget's virtualenv holds**, not just what `run.py` imports: `pip freeze > requirements.txt` from the virtualenv the local runs used. The build installs whatever is newest for anything left unpinned.
- **Every pinned version must have no known critical vulnerability.** The build scans the image and refuses one with a fixable CRITICAL CVE. The Creator's Test Run then fails with only *"The platform could not complete this run … this is not a problem with the widget"*, and no log. Check the pins before the upload, from any Python 3.9+ (here a throwaway virtualenv):

  ```bash
  python3 -m venv /tmp/audit && /tmp/audit/bin/pip install -q pip-audit && /tmp/audit/bin/pip-audit -r <widget>/requirements.txt
  ```

  `pip-audit` lists every known advisory, of any severity, while the build refuses only a fixable critical one. Move each flagged pin to a version `pip-audit` passes, and run the Cases again. Keep a flagged version only when the Widget needs that exact one (a pickled model saved with it) and none of its advisories is critical (look each id up), and say so in the hand-over.
- **Each version must install on Python 3.12 for Linux**: pure Python, or with a `cp312` `manylinux` wheel on PyPI. An old pin without one compiles from source during the build, and may need apt packages in `requirements.system`.

### What the uploader leaves out

The uploader leaves out what no Widget can depend on: `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.ipynb_checkpoints`, `.DS_Store`, `*.egg-info` and similar caches anywhere in the tree, any folder holding a virtualenv, and an `output/` folder. A `.env` **at the root** is left out too, and its variables are copied into Creator Environment (see [Secrets](#secrets-creator-environment)). A project may not contain `.docx`, `.pptx`, `.xlsx`, `.xls`, `.zip`, `.rar` or `.tar.gz` files: convert a bundled spreadsheet to CSV, and a document template to HTML or Markdown.

## The Fields: `interface.json`

The Widget Interface is an ordered list of Fields: the form a person fills on the Widget's page, and the `input` a caller sends through the API. Declare it in `interface.json` at the root, a JSON **array** of Field objects. The create wizard imports it on upload; one bad entry rejects the whole file, so keep it exact.

Every Field has:

| Key | Meaning |
|---|---|
| `type` | one of the eight below |
| `name` | the environment variable the run receives: a letter, then letters, digits or `_` (`^[a-zA-Z][a-zA-Z0-9_]*$`), unique in the list |
| `label` | what the form shows above the Field |
| `placeholder` | optional hint inside an empty Field |
| `default` | optional starting value |
| `isRequired` | `true` or `false`; write it on every Field, since a missing one counts as `true` |

The eight types and their own keys:

| `type` | For | Own keys |
|---|---|---|
| `text-field` | one line of text | `minLength`, `maxLength`, `pattern` (a regex) |
| `text-area` | several lines of text, or small JSON | `minLength`, `maxLength`, `pattern` |
| `number-field` | a number | `min`, `max`, `step` |
| `select` | one choice from a dropdown | `options`: a non-empty array of strings |
| `radio-group` | one choice, all shown | `options`: a non-empty array of strings |
| `checkbox-group` | several choices | `options`: a non-empty array of strings, `minItems`, `maxItems` |
| `date-field` | a calendar date | `fromYear`, `toYear` |
| `file` | one or more uploaded files | `mimes`, `multiple`, `maxFiles`, `maxFileSizeMB` |

- `options` are plain strings, never `{label, value}` objects: the string is both what the form shows and what the run receives.
- `mimes` is a list of **file extensions** without the dot: `["pdf"]`, `["csv", "txt"]`, `["png", "jpg"]` (`jpg` and `jpeg` are the same). A file whose extension is not listed is refused, and MIME types such as `image/png` match nothing. An empty list `[]` takes any file. Write `mimes` on every file Field.
- `maxFileSizeMB` caps one file below the platform's 512 MiB.
- `default` is the form's starting value only. A program calling through the API that leaves a Field out sends nothing for it, so `run.py` supplies its own default as well.
- `step` sets the form's increments only. Abyss refuses a number outside `min` and `max`, never one between steps, so `run.py` checks a whole number itself when that matters.
- A Field has no description or help text: put the hint in `label` and `placeholder`.
- Avoid the names `version` and `creator_ref`, which never reach the run, and `BUCKET_NAME`, `WIDGET_NAME`, `BASE_URL` and `INTERFACE_JSON`, which the platform overwrites.

**A Widget that takes either a few values or a file of them** (one customer's numbers, or a CSV of customers) marks every one of those Fields `"isRequired": false`. Its `run.py` fails with one sentence when the run has neither, only some, or both, and the file Field's `label` says it replaces the others.

```json
[
  {"type": "file", "name": "invoice", "label": "Invoice PDF", "isRequired": true, "mimes": ["pdf"], "multiple": false, "maxFileSizeMB": 20},
  {"type": "select", "name": "currency", "label": "Currency", "isRequired": true, "options": ["EUR", "USD", "GBP"], "default": "EUR"},
  {"type": "number-field", "name": "vat_rate", "label": "VAT rate (%)", "isRequired": false, "min": 0, "max": 50, "step": 0.5, "default": 20},
  {"type": "checkbox-group", "name": "sections", "label": "Sections to include", "isRequired": false, "options": ["summary", "lines", "totals"]},
  {"type": "date-field", "name": "due", "label": "Due date", "isRequired": false},
  {"type": "text-area", "name": "notes", "label": "Notes for the report", "isRequired": false, "maxLength": 2000}
]
```

## How inputs reach `run.py`

Each Field arrives as an environment variable named exactly like the Field, and its value is **always a string**:

| `type` | The variable holds |
|---|---|
| `text-field`, `text-area` | the text, trimmed at both ends |
| `number-field` | the number as text: `"3"`, `"2.5"` |
| `select`, `radio-group` | the chosen option |
| `checkbox-group` | a JSON array of the chosen options: `["summary","totals"]` |
| `date-field` | `MM/DD/YYYY`: `"03/15/2026"` |
| `file` | the file's path, relative to the folder's root: `"invoice.pdf"`. With `multiple: true`, a JSON array of paths in a folder named for the Field: `["photos/a.png","photos/b.png"]`, with a number in front of a repeated name (`photos/1-a.png`, `photos/2-a.png`) |

- **An optional Field left empty is absent or empty.** Read it with a default: `read("notes") or ""`.
- **Read the file at the path the variable names.** A single file lands at the folder's root under its uploaded name, stripped to letters, digits, `.`, `_`, ` ` and `-`. So never assume a fixed input file name, and never give a file you bundle at the root an extension a file Field's `mimes` accepts, since an upload of that name would replace it.
- **Newlines, tabs and backslashes arrive escaped.** Abyss hands every value over, Fields and secrets alike, with a newline as the two characters `\n`, a tab as `\t` and a backslash as `\\`. A text area, a JSON array holding `/` or a non-ASCII letter, and a multi-line secret all need decoding. Read every value through one helper that undoes it:

```python
import json
import os
import re

_ESCAPED = {"\\": "\\", "n": "\n", "t": "\t", "r": "\r"}


def read(name, default=None):
    """A Field's or a secret's value as it was typed, or default when it is empty."""
    value = os.environ.get(name, "")
    if value == "":
        return default
    return re.sub(r"\\([\\ntr])", lambda m: _ESCAPED[m.group(1)], value)


def read_list(name):
    """A checkbox-group's options, or a multi-file Field's paths."""
    value = read(name)
    return json.loads(value) if value else []
```

`scripts/run_local.py` hands values over the same way, so a Widget that skips the helper fails locally too.

## Outputs and the Result

- **Write every output file under `output/`**, relative to the folder's root (`os.makedirs("output", exist_ok=True)`). Subfolders are kept. Each file reaches the run's page, and the caller's `output_files`, under its path inside `output/`.
- **The Result** is `output/output.json`: valid JSON of at most 256 KB. It is what the caller reads as `run.result`, so put the answer there, in the shape a program would want: numbers as numbers, one key per fact. A Result that is missing, too big or not JSON is dropped (the run still succeeds), so write it last, after the files.
- **A run that writes nothing in `output/` fails**, even when `run.py` exits cleanly. Write at least the Result.
- Logs are what `run.py` prints, stdout and stderr together; the last 1000 lines are kept. Print progress and the reason for a failure there, never a secret.

## Secrets: Creator Environment

A key, a password or a token lives in **Creator Environment**, the Widget's encrypted variables, set by the Creator on the website and given to each run at its start as ordinary environment variables. Code reads them like any other variable (`read("OPENAI_API_KEY")`) and never contains one.

- A name is a letter or `_`, then letters, digits or `_`, at most 128 characters; a value is at most 8192 characters.
- A Field and a secret never share a name: when they do, the Field wins and the secret is dropped.
- Locally, the secrets live in a `.env` at the Widget folder's root (`NAME=value` lines), which the uploader keeps out of the upload and copies into Creator Environment. Keep that file out of version control. A Widget without secrets has no `.env`.

## Limits

| Limit | Value |
|---|---|
| One run | 30 minutes, then it is stopped |
| Machine | 2 shared CPUs, 4 GB of memory |
| One input file | 512 MiB, or the Field's `maxFileSizeMB` |
| One output file | 512 MiB |
| All of a run's outputs | 2 GiB |
| The project | 512 MiB |

A run may call the internet, such as a hosted model's API.

## How a run ends

| `run.py` | The run |
|---|---|
| exits 0 and wrote into `output/` | **succeeded** |
| exits non-zero (an uncaught exception, `sys.exit(1)`) | **failed** with `widget_fault` |
| exits 0 but `output/` is empty, or an output is over a limit | **failed** with `widget_fault` |
| is still running at 30 minutes | **failed** with `budget_exceeded` |

When the input is wrong (a PDF that is not an invoice, a CSV missing a column), print one plain sentence saying what is wrong and exit non-zero. A person who ran it on the website reads that sentence in the run's log. A program calling through the API gets only the failed run: `widget_fault` and *"Error encountered while executing run.py"*, never your sentence. Three failed runs in a row take a public Widget off the Catalog until its Creator's next succeeded run, so a bad input fails cleanly and a good input never fails.

## A complete `run.py`

```python
"""Counts the words in a text file and writes a summary."""
import json
import os
import re
import sys

_ESCAPED = {"\\": "\\", "n": "\n", "t": "\t", "r": "\r"}


def read(name, default=None):
    value = os.environ.get(name, "")
    if value == "":
        return default
    return re.sub(r"\\([\\ntr])", lambda m: _ESCAPED[m.group(1)], value)


def main():
    path = read("document")
    if not path or not os.path.isfile(path):
        sys.exit("No document arrived.")
    top = int(read("top", "10"))

    with open(path, encoding="utf-8", errors="replace") as f:
        words = re.findall(r"[\w']+", f.read().lower())
    counts = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]

    os.makedirs("output", exist_ok=True)
    with open("output/top-words.csv", "w", encoding="utf-8") as f:
        f.write("word,count\n")
        f.writelines(f"{word},{n}\n" for word, n in ranked)
    with open("output/output.json", "w", encoding="utf-8") as f:
        json.dump({"words": len(words), "distinct": len(counts), "top": dict(ranked)}, f)


if __name__ == "__main__":
    main()
```

with this `interface.json`:

```json
[
  {"type": "file", "name": "document", "label": "A text file", "isRequired": true, "mimes": ["txt", "md"], "multiple": false},
  {"type": "number-field", "name": "top", "label": "How many words to list", "isRequired": false, "min": 1, "max": 100, "step": 1, "default": 10}
]
```
