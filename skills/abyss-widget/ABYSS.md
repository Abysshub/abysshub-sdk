# Putting a Widget on Abyss

The Creator does this on the website, signed in; you prepare everything and tell them each step. It makes the Widget private, so only the Creator, and whoever they give its private link to, can run it.

## 0. Is the Abyss step open yet?

The Abyss step needs Abyss's API, `/v1`, which opens on abysshub.com soon. Check that it answers before you ask the Creator to do anything, at the address `check_abyss.py` will use (`ABYSS_BASE_URL` when it is set, in the shell or in `port/.env`):

```bash
curl -s -o /dev/null -w "%{http_code}\n" "${ABYSS_BASE_URL:-https://api.abysshub.com}/v1/openapi.json"
```

Anything but `200` means the Abyss step isn't available yet. Tell the Creator so, end with the local runs (for a Port, write it into `CHECK.md`), and hand over the Widget folder for them to upload once Abyss opens.

The website is the one whose API that is: abysshub.com for `https://api.abysshub.com`, and for an `ABYSS_BASE_URL` of `https://api.<site>`, `<site>`.

## 1. Prepare

- `<widget>/` holds `run.py`, `requirements.txt`, `interface.json`, and the code's other files, and `pip-audit` passes its pins (WIDGET.md, "Dependencies").
- `<widget>/.env` holds every secret the Widget reads, and nothing else. A Widget without secrets has none.
- A thumbnail: any PNG or JPEG of at most 5 MB. The Creator may have one; otherwise make a plain one, kept in `port/` (`work/` for a built Widget), never inside `<widget>/`.
- One input to run first: a Case marked `"abyss": true`, or a sample input for a built Widget, with its files at hand.

## 2. The Creator uploads and publishes it

Give the Creator these steps, with the names filled in:

1. On the website, open **Create** (the Cave's *Your Widgets* section, or `/widgets/create`).
2. **Upload & interface.** Drag the Widget folder onto *Drag & drop your project folder here*, or use **Add folder**. A folder, not a zip.
   - *Interface auto-generated from interface.json — N fields added* confirms the Fields.
   - *interface.json found but not applied* means it is invalid: its message names the problem, which is yours to fix before they upload again.
   - *Left out: … .env → Environment variables* is expected: the uploader keeps the secrets out of the upload.
3. **Environment variables**, on the same page: *Imported from .env: N added (…)* lists the secrets' names. They add any missing one with **+ Add variable**. With no secrets, there is nothing to add.
4. Press **Test Run**, fill the form with the input from step 1, and press **RUN**. It must succeed: Abyss publishes only a version whose Test Run succeeded.
   - A failure with a log: the log says why. Fix the Widget, run it locally again, and have them upload the folder again as a new Draft (any change needs a new Test Run).
   - *The platform could not complete this run … this is not a problem with the widget*, with no log, right after an upload: usually the build refusing a dependency with a known critical vulnerability. Run `pip-audit` on the pins, move the flagged one, run the Cases again, and have them upload again. When `pip-audit` passes, the fault may be the platform's: have them press **Run again**.

   Then **Continue**.
5. **Finalize.** A title of 3 to 96 characters, at least one tag, the thumbnail, and **PRIVATE** (a new Widget starts as PUBLIC). The price may stay 0. Press **Publish**.
6. They copy the Widget page's address from the browser, `…/widgets/<number>/<name>`, and give it to you.

A Draft left untouched for a week is deleted.

## 3. An API key, for the runs you make

In the Cave, under **Your API keys**, the Creator presses **Create a key**, names it, and sets a small **Monthly Spend Cap**. The key is shown once. They put it in `port/.env` (`work/.env` for a built Widget) as `ABYSS_API_KEY=…` themselves: never in this conversation, and never in `<widget>/.env`, whose variables reach every run of the Widget.

On the website, a Creator's runs of their own Widget cost nothing. Through the API, each run carries a call price of 0.1 Byssium once the account has made its first 100 API runs, so a run's `price` may read 0.1; a failed run costs nothing.

## 4. Run it

For a Port, run the Abyss Check (PORT.md, step 8). For a built Widget, the Test Run was its first run on Abyss. When the Creator wants your other samples run there too, mark them `"abyss": true`, and run them as PORT.md's step 8 does, with `work/` in place of `port/`.
