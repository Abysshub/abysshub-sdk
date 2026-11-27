# Putting a Widget on Abyss

There are two ways, and the Creator's API key picks one:

- **The command**, when their key has **Manage Widgets**: you publish the Widget yourself with `abysshub publish`, from the `abysshub` Python library, and end with the link it prints (step 3).
- **The website**, when it has not: the Creator uploads and publishes it, signed in, and you tell them each step (step 4).

Either way the Widget is **Private**: only the Creator, and whoever they give its private link to, can run it. It is listed for everyone only when the Creator asks you to list it; never set `"visibility": "public"` on your own.

Follow this file only when the Creator chose to put it on Abyss (PORT.md, step 3; SKILL.md, "Build a Widget", step 1). When they chose the folder only, skip every step here: make no thumbnail, ask for no API key, and run no Abyss Check. Hand over the Widget folder, the result of the local runs (for a Port, `CHECK.md` says the Abyss step was not asked for), and step 4's upload steps for later. It is the same ending as when Abyss can't be reached.

`port/` below is `work/` for a built Widget.

## 0. Can Abyss be reached?

The Abyss step needs Abyss's API, `/v1`. Check that it answers before you ask the Creator to do anything, at the address the command and `check_abyss.py` will use: `ABYSS_BASE_URL` when it is set, in the shell or in `port/.env`; else `https://api.dev.abysshub.com` when the key in `port/.env` starts `abyss_sk_dev_`; else `https://api.abysshub.com`:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "${ABYSS_BASE_URL:-https://api.abysshub.com}/v1/openapi.json"
```

With a dev key and no `ABYSS_BASE_URL`, put `https://api.dev.abysshub.com` in place of `https://api.abysshub.com`.

Anything but `200` means Abyss can't be reached right now. Tell the Creator so, end with the local runs (for a Port, write it into `CHECK.md`), and hand over the Widget folder, with step 4's upload steps, for them to upload later.

The website is the one whose API that is: abysshub.com for `https://api.abysshub.com`, dev.abysshub.com for `https://api.dev.abysshub.com`, and for an `ABYSS_BASE_URL` of `https://api.<site>`, `<site>`.

## 1. An API key

In the Cave, under **Your API keys**, the Creator presses **Create a key**, names it, switches **Manage Widgets** on, and sets a small **Monthly Spend Cap**. A key is never given Manage Widgets after it is made, so a key they already have without it means a new one. The key is shown once. They put it in `port/.env` as `ABYSS_API_KEY=…` themselves: never in this conversation, and never in `<widget>/.env`, whose variables reach every run of the Widget.

The same key publishes the Widget and makes your runs on it (step 5). A Creator who would rather not give you a key that manages Widgets makes one without it: then they publish on the website (step 4), and the key makes your runs only.

Install the library once, beside the Widget, and run it with the key from `port/.env`, never printing the key:

```bash
python3 -m venv port/.venv-check && port/.venv-check/bin/pip install abysshub
(set -a && . port/.env && set +a && port/.venv-check/bin/abysshub publish <widget>)
```

On the website, a Creator's runs of their own Widget cost nothing, and so does a Test Run. Through the API, each run carries a call price of 0.1 Byssium once the account has made its first 100 API runs, so a run's `price` may read 0.1; a failed run costs nothing.

## 2. Prepare

- `<widget>/` holds `run.py`, `requirements.txt`, `interface.json`, and the code's other files, and `pip-audit` passes its pins (WIDGET.md, "Dependencies").
- `<widget>/.env` holds every secret the Widget reads, and nothing else. A Widget without secrets has none. Neither the command nor the website uploads it: both put its variables into Creator Environment.
- **The Test Run's input**: one real, ordinary use that succeeds. For a Port, one of the Cases marked `"abyss": true`; for a built Widget, one of the samples. Its run becomes the **Example Run** on the Widget's page, its inputs and outputs shown there, so pick one the Creator is glad to show, never a client's data, and never the one that should fail.
- **The listing**:
  - a **title** of 3 to 96 characters that says what the Widget does (*CSV Cleaner*, *Invoice to bill*);
  - one to five **tags**, the lower-case words a person would search for;
  - a **description** of one or two sentences: what one run takes and what it hands back (for a Port, the Done List's "What one run does");
  - the **price**, 0 unless the Creator names one.
- **A thumbnail**: a PNG or JPEG of at most 5 MB, made from the real result of the Test Run's input as your local run produced it: the chart it drew, the first page of the document it wrote, or its Result set out as a plain card. The Creator may have one of their own instead. It goes at `<widget>/thumbnail.png` for the command, which never uploads it, and in `port/` for the website, which would.

## 3. With the command

### Write the two files

At the root of `<widget>/`, beside `interface.json`:

- **The Publish File**, `abyss.json`, holds the listing from step 2 and the thumbnail's path inside the folder:

  ```json
  {
    "title": "CSV Cleaner",
    "tags": ["csv", "data"],
    "description": "Removes empty rows and repeated rows from a CSV file.",
    "visibility": "private",
    "price": 0,
    "free_runs": 0,
    "thumbnail": "thumbnail.png"
  }
  ```

  `"visibility": "private"` stays unless the Creator asked you to list the Widget; `free_runs` (0 to 10) matters only on a paid one. The command writes a `widget` block into this file as it goes: which Widget the folder is, and what it was at the last publish or pull. Never write or edit that block; keep the file with the folder (and in version control, when the project is under it), since it is how a later publish finds the same Widget.
- **The Test Inputs**, `test_inputs.json`, hold the Test Run's input from step 2: a JSON object with one value for each Field's name, written as a Case's `input` is (PORT.md, step 2), except that a file Field's value is the path of a file inside `<widget>/` as a plain string, never `{"file": …}`, or a list of paths for a multi-file Field. Copy that file from the Case into `<widget>/test/`, never at the root (WIDGET.md, "How inputs reach `run.py`"). A Field it leaves out takes its `default`.

  ```json
  {"table": "test/customers.csv", "drop_empty": "yes"}
  ```

The command uploads `test_inputs.json` and the files it names with the rest of the folder, and never uploads the Publish File, the thumbnail it names, or a root `.env`.

### Publish

```bash
(set -a && . port/.env && set +a && port/.venv-check/bin/abysshub publish <widget>)
```

It asks nothing: it goes or it stops. Before it sends anything that changes a Widget, it checks the folder and the key and prints every fault at once. Then it makes a Draft, sends the folder (each `Left out …` line is a file it kept back), puts the root `.env`'s variables into Creator Environment (each name with what became of it, never a value), makes the Test Run from the Test Inputs and waits for it, saves the listing, publishes, and prints the Widget's link as its last line: its private link, for a Private Widget. Give the Creator that link. **The Widget is on Abyss.**

An environment name it calls **kept** is one the Widget already holds with another value, which stays. When the Creator says the file's value is the new one (a changed key, usually), publish again with `--use-env-file`.

### When it stops

It exits non-zero, and each line `abysshub: stopped: <code>: <message>` says why:

- **A fault in the folder** (`title_missing`, `tag_missing`, `thumbnail_missing`, `thumbnail_not_image`, `run_py_missing`, `requirements_missing`, `publish_file_missing`, `publish_file_invalid`, `test_inputs_invalid`, `interface_invalid`, `env_invalid`): fix every one it printed and publish again. Nothing was sent.
- **A fault in the Test Inputs**: `test_input_missing` is a required Field with neither a value in `test_inputs.json` nor a `default`; `test_input_unknown` names no Field of `interface.json`; `test_input_file_missing` names no file inside the folder. Fix `test_inputs.json`. A secret the Widget needs and Creator Environment lacks shows up instead as a failed Test Run: the Creator adds it to `<widget>/.env`.
- **The key**: `invalid_api_key` is no key, or one Abyss refuses; `manage_widgets_required` is a key without Manage Widgets. The Creator makes one with it (step 1), or publishes on the website (step 4): move the thumbnail into `port/` first, since the website uploads the whole folder.
- **The Test Run failed** (`widget_fault`, `platform_fault`, `budget_exceeded`): the run's logs are printed above the stop, and nothing was published. Read them as step 4's Test Run says (a build refused for a vulnerable pin, a pin that does not install, your own code's fault), fix the Widget, run it locally again, and publish again: it takes up the same Draft.
- **`listing_field_refused`**: Abyss refused a value of the Publish File, which `param` names; fix it and publish again.
- **`widget_moved`**: someone changed the Widget on the website since this folder's last publish or pull: its listing, its code, or both. Nothing was sent. Run `abysshub status <widget>` (with the key, as above): it changes nothing and shows the live Widget beside the folder. Show the Creator what moved, and ask:
  - a listing changed on the website: `abysshub pull <widget>` takes it into `abyss.json` and the thumbnail, then publish again;
  - code published from the website: only `abysshub publish --force <widget>` replaces it with the folder's. Use `--force` only when the Creator says the folder wins.
- `rate_limited`, `server_error` or a dropped connection, after the command's own retries: publish again; it takes up the same Draft.
- Any other code: its message says what to fix. Fix it and publish again.

## 4. On the website

When you run on the Creator's computer, open the website's **Create** page, `https://<site>/widgets/create`, in their browser, and the Widget folder in their file manager:

- macOS: `open "https://<site>/widgets/create"` and `open "<widget>"`
- Linux: `xdg-open "https://<site>/widgets/create"` and `xdg-open "<widget>"`
- Windows: `start "" "https://<site>/widgets/create"` and `start "" "<widget>"`

Then tell them to drag that folder onto *Drag & drop your project folder here*. When you do not run on their computer (a cloud session, for example), give them the page's address and the folder's full path instead.

Give the Creator these steps, with the names filled in:

1. On the website, open **Create** (the Cave's *Your Widgets* section, or `/widgets/create`).
2. **Upload & interface.** Drag the Widget folder onto *Drag & drop your project folder here*, or use **Add folder**. A folder, not a zip.
   - *Interface auto-generated from interface.json — N fields added* confirms the Fields.
   - *interface.json found but not applied* means it is invalid: its message names the problem, which is yours to fix before they upload again.
   - *Left out: … .env → Environment variables* is expected: the uploader keeps the secrets out of the upload.
   - *Not used: Dockerfile, .dockerignore — Abyss builds from requirements.txt and requirements.system.* shows when the project has a Dockerfile: whatever it installs must be in those two files (WIDGET.md, "What the uploader leaves out").
3. **Environment variables**, on the same page: *Imported from .env: N added (…)* lists the secrets' names. They add any missing one with **+ Add variable**. With no secrets, there is nothing to add.
   - When they upload again, *N kept with a different value in your .env: …* names the secrets whose value changed in `.env`, a new key for instance. The website's values stay until they press **Use the file's values**, offered only right after the pick.
4. Press **Test Run**, fill the form with the Test Run's input from step 2, and press **RUN**. It must succeed: Abyss publishes only a version whose Test Run succeeded.
   - A failure with a log: the log says why. Fix the Widget, run it locally again, and have them upload the folder again as a new Draft (any change needs a new Test Run).
   - *This Widget's build was refused: …*: a package the Widget installs has a known critical vulnerability. The message names each package, its installed version, its CVE ids and the version that fixes it. Move each named package to its fixed version or later, run the Cases again, and have them upload again.
   - *The platform could not complete this run … this is not a problem with the widget*, with no log: the platform's fault, or a build that could not install the Widget's packages (an unpinned or uninstallable version; see WIDGET.md, "Each version must install on Python 3.12 for Linux"). Check that every pin installs: fix one that does not, run the Cases again, and have them upload again. When every pin installs, have them press **Run again**.

   Then **Continue**.
5. **Finalize.** The title, tags and description from step 2, the thumbnail, and **PRIVATE** (a new Widget starts as PUBLIC), unless they want it listed. The price may stay 0. Press **Publish**.
6. They copy the Widget page's address from the browser, `…/widgets/<number>/<name>`, and give it to you.

A Draft left untouched for a week is deleted.

## 5. Run it

For a Port, run the Abyss Check (PORT.md, step 8). For a built Widget, the Test Run was its first run on Abyss. When the Creator wants your other samples run there too, mark them `"abyss": true`, and run them as PORT.md's step 8 does, with `work/` in place of `port/`. The Widget's address for `check_abyss.py` is the `id` in `abyss.json`'s `widget` block, or the page's address the Creator gave you.

## 6. A later change

A change to a published Widget (a fix, a new Field, a new listing) is made in the same folder. Run the Cases or samples locally again, keep `test_inputs.json` in step with `interface.json`, and then:

- **with the command**, run `abysshub publish <widget>` again. It shows the live Widget beside the folder first, then publishes a new version of the same Widget, saves only the Listing Fields that changed, and prints the same link;
- **on the website**, the Creator uploads the folder again and makes its Test Run, as in step 4.
