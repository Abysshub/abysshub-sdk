---
name: abyss-widget
description: Builds an Abyss Widget, or ports a tool the user already has (an n8n flow, a Python script, a notebook, a Streamlit or Gradio app) into one and checks it on real uses. Use when the user wants to make, build or publish an Abyss (abysshub) Widget, or to port, move or bring a flow, script, notebook or app to Abyss.
---

# Abyss Widget

An **Abyss Widget** is a Python project that Abyss runs on demand: a person fills its form on abysshub.com, or a program calls it through the Abyss API, and one run turns those inputs into a **Result** (JSON) and files. You write the Widget; its **Creator**, the person you are working with, puts it on Abyss.

In short (WIDGET.md has every rule):

- **The project:** `run.py` at the root, `requirements.txt` (pinned), an optional `requirements.system` of apt packages, and any other files. Python 3.12 on Ubuntu is the only runtime.
- **The Widget Interface:** the Fields, declared in `interface.json`, of eight types: `text-field`, `text-area`, `number-field` (`min`/`max`), `select`, `radio-group`, `checkbox-group`, `date-field` and `file` (`mimes`, `multiple`, `maxFileSizeMB`). Each Field's name reaches the run as an environment variable; a file Field's is the path of the file.
- **Outputs:** files written to `output/`. The Result is `output/output.json`, valid JSON of at most 256 KB.
- **Limits:** 30 minutes, 2 CPUs and 4 GB, 512 MiB per input file, 512 MiB per output file, 2 GiB per run.
- **Secrets:** in **Creator Environment**, the Widget's encrypted variables, given to each run at its start. Never in code.

## When Abyss is the wrong tool

Say so, say why, and stop, when what the Creator wants is:

- a full web app, with accounts or pages of its own;
- a long-running server, a bot, or anything that must stay up between requests;
- something driven by triggers or schedules, whose work is the watching and reacting (a sync, a monitor, an inbox rule);
- something that needs a person to sign in interactively on every run.

A Widget is one run: inputs in, work done, a Result and files out. When the tool *contains* such a function (a flow whose webhook hands one file to some steps that answer), the function is a Widget and the trigger stays outside; see PORT.md, step 1.

## Pick the path

- **Port**: the Creator has the tool already, as an n8n flow export, a script, a notebook or an app. Read PORT.md and follow its steps; the words **Port**, **Case**, **Done List** and **Check** are defined there.
- **Build**: the tool does not exist yet. Follow the steps below.

## Build a Widget

1. **Shape it.** Agree with the Creator what one run takes (each input, its type, which are required) and what it hands back (the Result's keys, the files). Write that down as the Fields and the outputs, and check them against the limits.
2. **Write it** by WIDGET.md: `interface.json`, `run.py` (inputs read through its `read()` helper, outputs under `output/`, secrets from the environment), `requirements.txt` pinned and passed by `pip-audit` (WIDGET.md, "Dependencies"), and the secrets' names for the Creator to put in `<widget>/.env`.
3. **Run it here.** Write two or three sample inputs, plus one that should fail cleanly, as `work/cases/<sample>/case.json` beside the Widget folder (the format is in PORT.md, step 2), make a Python 3.12 virtualenv at `work/.venv` with the requirements, and run them all (`<this skill>` is the folder holding this file):

   ```bash
   python3 <this skill>/scripts/run_local.py <widget> work/cases/*
   ```

   Each run's `run.json`, `log.txt` and `output/` land in `work/runs/local/<sample>/`. Read them: a run that should succeed succeeded, its Result and files are what step 1 said, and the bad input failed with a clear sentence in its log. Fix and run again until that holds.
4. **Put it on Abyss** by ABYSS.md.

**Done when** the samples pass here, and the Creator has published it, or ABYSS.md's first step says the Abyss step isn't available yet and you have handed over the folder.

## The files of this skill

- **WIDGET.md**: what a Widget must be: the project, every Field type, how inputs arrive, outputs, secrets, limits, how a run ends.
- **PORT.md**: the Port path, from Fit to hand-over.
- **ABYSS.md**: how the Creator puts a Widget on Abyss privately, and the API key you use.
- **scripts/run_local.py**: runs a Widget on this machine the way Abyss runs it (standard library only).
- **scripts/check_abyss.py**: runs Cases on Abyss through the API, and prints the Widget's private link (needs `pip install abysshub`).
