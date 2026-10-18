#!/usr/bin/env python3
"""Run an Abyss Widget on this machine the way Abyss runs it.

    python3 run_local.py <widget-folder> <case-folder> [<case-folder> ...]

Each case folder holds a case.json, {"input": {...}, "needs": [...]}, where a
file Field's value is {"file": "<path relative to the case folder>"} (a list of
them for a multi-file Field), a date is "YYYY-MM-DD", and "needs" names the
secrets the run needs: a Case whose secret is missing from the Widget folder's
.env is reported "not run", never run. The run copies the Widget folder
as the uploader would, hands every input over as Abyss does (as strings, each
exactly as it was sent), adds the secrets in the Widget folder's .env, runs
`python run.py` in a clean environment, then judges the ending by Abyss's
rules. It writes run.json, log.txt and output/ to
<port>/runs/local/<case>/, where <port> is the folder holding cases/.

Options:
    --python PATH   the interpreter to run with (default: <port>/.venv, else this one)
    --out DIR       where to write the runs (default: <port>/runs/local)
    --timeout SECS  the run's limit (default: 1800, Abyss's 30 minutes)

Standard library only; Python 3.9+.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ABYSS_PYTHON = "3.12"
RESULT_MAX_BYTES = 256 * 1024
OUTPUT_FILE_MAX_BYTES = 512 * 1024 * 1024
OUTPUTS_MAX_BYTES = 2 * 1024 * 1024 * 1024
INPUT_FILE_MAX_BYTES = 512 * 1024 * 1024

JUNK_NAMES = {
    ".git", ".svn", ".hg", ".idea", ".vscode", ".DS_Store", "node_modules", "__pycache__",
    ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    ".ipynb_checkpoints", ".eggs",
}
REFUSED_SUFFIXES = (".docx", ".pptx", ".xlsx", ".xls", ".zip", ".rar", ".tar.gz")
DROPPED_NAMES = {"version", "creator_ref"}
PLATFORM_NAMES = ("BUCKET_NAME", "WIDGET_NAME", "BASE_URL", "INTERFACE_JSON")
RESERVED_SECRETS = set(PLATFORM_NAMES) | {
    "WIDGET_CALLBACK_IDENTITY", "AWS_BATCH_JOB_ID", "WIDGET_CLAIM_TOKEN", "WIDGET_CLAIM_URL",
}
FIELD_TYPES = {
    "text-field", "text-area", "number-field", "radio-group", "checkbox-group", "select", "date-field", "file",
}


class Refused(Exception):
    """The upload or the input would be refused before any run starts."""


def is_junk(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if rel.parts[0] == "output" or (len(rel.parts) == 1 and (rel.name == ".env" or rel.name.startswith(".env."))):
        return True
    if any(part in JUNK_NAMES or part.endswith(".egg-info") for part in rel.parts):
        return True
    return path.is_dir() and ((path / "pyvenv.cfg").exists() or (path / "conda-meta").is_dir())


def copy_project(widget: Path, dest: Path) -> list[str]:
    """Copy the Widget folder as the uploader keeps it; return the notes worth printing."""
    notes = []
    if not (widget / "run.py").is_file():
        raise Refused("the Widget folder has no run.py at its root")
    if not (widget / "requirements.txt").is_file():
        raise Refused("the Widget folder has no requirements.txt at its root (an empty one is fine)")
    total = 0
    for dirpath, dirnames, filenames in os.walk(widget):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not is_junk(here / d, widget)]
        for name in filenames:
            src = here / name
            if is_junk(src, widget):
                continue
            rel = src.relative_to(widget)
            if name.lower().endswith(REFUSED_SUFFIXES):
                raise Refused(f"{rel} is a file type a project may not contain")
            total += src.stat().st_size
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
    if total > 512 * 1024 * 1024:
        raise Refused(f"the project is {total / 2**20:.0f} MiB; the limit is 512 MiB")
    system = widget / "requirements.system"
    if system.is_file() and system.read_text().split():
        notes.append("requirements.system lists apt packages, which a local run does not install: install them here by hand")
    return notes


def load_fields(widget: Path) -> list[dict]:
    path = widget / "interface.json"
    if not path.is_file():
        return []
    fields = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(fields, list):
        raise Refused("interface.json must be a JSON array of Fields")
    names = set()
    for i, field in enumerate(fields):
        if not isinstance(field, dict) or field.get("type") not in FIELD_TYPES:
            raise Refused(f"interface.json entry {i} has no known type")
        name = field.get("name", "")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,255}", str(name)) or name in names:
            raise Refused(f"interface.json entry {i} has a bad or repeated name: {name!r}")
        names.add(name)
        if field["type"] in ("select", "radio-group", "checkbox-group"):
            options = field.get("options")
            if not options or not all(isinstance(o, str) for o in options):
                raise Refused(f"Field {name}: options must be a non-empty array of strings")
        if field["type"] == "file" and not isinstance(field.get("mimes", []), list):
            raise Refused(f"Field {name}: mimes must be an array of file extensions")
    return fields


def sanitize(path: str) -> str:
    """The platform's cleaning of an uploaded file's name."""
    segments = []
    for segment in path.strip().replace("\\", "/").lstrip("/").split("/"):
        segment = segment.strip()
        if segment in ("", ".", ".."):
            continue
        segment = re.sub(r"[^A-Za-z0-9._ -]", "", segment)
        if segment:
            segments.append(segment)
    return "/".join(segments)[:255]


def number_repeats(leaves: list[str]) -> list[str]:
    counts = {leaf: leaves.count(leaf) for leaf in leaves}
    numbered: dict[str, int] = {}
    out = []
    for leaf in leaves:
        if counts[leaf] == 1:
            out.append(leaf)
            continue
        while True:
            numbered[leaf] = numbered.get(leaf, 0) + 1
            name = f"{numbered[leaf]}-{leaf}"
            if name not in counts:
                break
        out.append(name)
    return out


def compact_json(value) -> str:
    """A list as the run receives it: no spaces, with / and non-ASCII letters as themselves."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def check_input(fields: list[dict], given: dict) -> None:
    """The refusals /v1 would answer with invalid_input, in its order."""
    by_name = {f["name"]: f for f in fields}
    for name in given:
        if fields and name not in by_name:
            raise Refused(f"invalid_input: {name} is not a Field of this Widget")
    for field in fields:
        name, kind = field["name"], field["type"]
        value = given.get(name)
        empty = value is None or value == "" or value == []
        if empty:
            if field.get("isRequired", True) is True:
                raise Refused(f"invalid_input: {name} is required")
            continue
        if kind in ("text-field", "text-area"):
            if not isinstance(value, str):
                raise Refused(f"invalid_input: {name} takes a string")
            if field.get("minLength") and len(value) < int(field["minLength"]):
                raise Refused(f"invalid_input: {name} is shorter than {field['minLength']}")
            if field.get("maxLength") and len(value) > int(field["maxLength"]):
                raise Refused(f"invalid_input: {name} is longer than {field['maxLength']}")
        elif kind in ("select", "radio-group"):
            if value not in field["options"]:
                raise Refused(f"invalid_input: {name} must be one of {field['options']}")
        elif kind == "checkbox-group":
            if not isinstance(value, list) or any(v not in field["options"] for v in value):
                raise Refused(f"invalid_input: {name} takes a list drawn from {field['options']}")
        elif kind == "number-field":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise Refused(f"invalid_input: {name} takes a number")
            if field.get("min") is not None and number < float(field["min"]):
                raise Refused(f"invalid_input: {name} is below {field['min']}")
            if field.get("max") is not None and number > float(field["max"]):
                raise Refused(f"invalid_input: {name} is above {field['max']}")
        elif kind == "date-field":
            try:
                datetime.date.fromisoformat(str(value))
            except ValueError:
                raise Refused(f"invalid_input: {name} takes a date as YYYY-MM-DD")


def place_files(field: dict, value, case: Path, run_dir: Path) -> str:
    """Copy a file Field's files into the run folder; return the variable's value."""
    many = bool(field.get("multiple"))
    items = value if isinstance(value, list) else [value]
    if not many and len(items) != 1:
        raise Refused(f"invalid_input: {field['name']} takes one file")
    mimes = [m.lower().lstrip(".") for m in field.get("mimes", [])]
    sources = []
    for item in items:
        if not isinstance(item, dict) or "file" not in item:
            raise Refused(f'invalid_input: {field["name"]} takes {{"file": "<path>"}} in case.json')
        src = (case / item["file"]).resolve()
        if not src.is_file():
            raise Refused(f"{field['name']}: {src} does not exist")
        ext = src.suffix.lower().lstrip(".")
        if mimes and not (ext in mimes or (ext in ("jpg", "jpeg") and {"jpg", "jpeg"} & set(mimes))):
            raise Refused(f"held_input refused: {src.name} is not one of {mimes}")
        limit = min(INPUT_FILE_MAX_BYTES, float(field.get("maxFileSizeMB") or 512) * 1024 * 1024)
        if src.stat().st_size > limit:
            raise Refused(f"held_input refused: {src.name} is over {limit / 2**20:g} MiB")
        sources.append(src)
    if not many:
        rel = sanitize(sources[0].name) or "input"
        shutil.copy2(sources[0], run_dir / rel)
        return rel
    folder = sanitize(field["name"])
    leaves = number_repeats([Path(sanitize(s.name)).name or "input" for s in sources])
    paths = []
    for src, leaf in zip(sources, leaves):
        (run_dir / folder).mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, run_dir / folder / leaf)
        paths.append(f"{folder}/{leaf}")
    return compact_json(paths)


def as_variable(field: dict | None, value) -> str | None:
    """A non-file input as the run receives it; None when it arrives empty."""
    if value is None or value == "" or value == []:
        return None
    kind = field["type"] if field else None
    if kind == "date-field":
        day = datetime.date.fromisoformat(str(value))
        return f"{day.month:02d}/{day.day:02d}/{day.year:04d}"
    if isinstance(value, (list, dict)):
        return compact_json(value)
    if isinstance(value, bool):
        return "true" if value else ""
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return str(value).strip()


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def interpreter(arg: str | None, port: Path) -> tuple[str, str | None]:
    """The Python to run with, and a note when it is not the one asked for or expected."""
    if arg:
        if os.sep in arg or "/" in arg:
            return os.path.abspath(arg), None  # never resolve(): a virtualenv's python is a symlink
        return shutil.which(arg) or arg, None
    for candidate in (port / ".venv" / "bin" / "python", port / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate), None
    return sys.executable, f"no {port / '.venv'}, so this ran on {sys.executable}, which may lack the Widget's requirements"


def run_case(widget: Path, case: Path, out_root: Path, python: str, timeout: int) -> dict:
    spec = json.loads((case / "case.json").read_text(encoding="utf-8"))
    missing = [name for name in spec.get("needs", []) if name not in read_dotenv(widget / ".env")]
    given = spec.get("input", {})
    fields = load_fields(widget)
    by_name = {f["name"]: f for f in fields}
    out = out_root / case.name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    report: dict = {"case": case.name, "where": "local", "status": None, "error": None, "result": None,
                    "output_files": [], "notes": []}
    if missing:
        report["status"] = "not run"
        report["error"] = {"code": "not_run", "message": "needs " + ", ".join(missing) + f" in {widget / '.env'}"}
        (out / "run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    with tempfile.TemporaryDirectory(prefix="abyss-run-") as tmp:
        run_dir = Path(tmp) / "widget"
        run_dir.mkdir()
        try:
            report["notes"] += copy_project(widget, run_dir)
            check_input(fields, given)
            variables: dict[str, str] = {}
            for name, value in given.items():
                if name in DROPPED_NAMES:
                    continue
                field = by_name.get(name)
                if field and field["type"] == "file":
                    if value not in (None, "", []):
                        variables[name] = place_files(field, value, case, run_dir)
                    continue
                text = as_variable(field, value)
                if text is not None:
                    variables[name] = text
        except Refused as refusal:
            report["status"] = "refused"
            report["error"] = {"code": "refused", "message": str(refusal)}
            (out / "run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            return report

        (run_dir / "output").mkdir(exist_ok=True)
        env = {k: os.environ[k] for k in ("HOME", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "LANG") if k in os.environ}
        env["PATH"] = os.pathsep.join([str(Path(python).parent), os.environ.get("PATH", "")])
        env["PYTHONUTF8"] = "1"
        env.update(variables)
        interface_text = (widget / "interface.json").read_text(encoding="utf-8") if fields else "[]"
        platform = {"BUCKET_NAME": "local", "WIDGET_NAME": widget.name, "BASE_URL": "http://localhost",
                    "INTERFACE_JSON": json.dumps(json.loads(interface_text), separators=(",", ":"))}
        env.update(platform)
        for name, value in read_dotenv(widget / ".env").items():
            if name in by_name:
                report["notes"].append(f"secret {name} is dropped: a Field has the same name")
            elif name in RESERVED_SECRETS or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
                report["notes"].append(f"secret {name} is a name Creator Environment refuses")
            else:
                env[name] = value

        version = subprocess.run([python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                                 capture_output=True, text=True).stdout.strip()
        if version != ABYSS_PYTHON:
            report["notes"].append(f"ran on Python {version}; Abyss runs Python {ABYSS_PYTHON}")
        report["python"] = version

        started = time.monotonic()
        with open(out / "log.txt", "wb") as log:
            try:
                code = subprocess.run([python, "run.py"], cwd=run_dir, env=env, stdout=log,
                                      stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                code = 124
        report["seconds"] = round(time.monotonic() - started, 1)

        output = run_dir / "output"
        files = sorted(p for p in output.rglob("*") if p.is_file())
        sizes = {p.relative_to(output).as_posix(): p.stat().st_size for p in files}
        report["output_files"] = [{"path": path, "size": size} for path, size in sizes.items()]
        if output.exists():
            shutil.copytree(output, out / "output")

        if code == 124:
            report["error"] = {"code": "budget_exceeded", "message": f"run.py was still running at {timeout} s"}
        elif code != 0:
            report["error"] = {"code": "widget_fault", "message": f"run.py exited with {code}; see log.txt"}
        elif not files:
            report["error"] = {"code": "widget_fault", "message": "output/ is empty: write at least output/output.json"}
        elif any(size > OUTPUT_FILE_MAX_BYTES for size in sizes.values()):
            report["error"] = {"code": "widget_fault", "message": "an output file is over 512 MiB"}
        elif sum(sizes.values()) > OUTPUTS_MAX_BYTES:
            report["error"] = {"code": "widget_fault", "message": "the outputs are over 2 GiB together"}
        report["status"] = "failed" if report["error"] else "succeeded"

        result = output / "output.json"
        if report["status"] == "succeeded" and result.is_file():
            if result.stat().st_size > RESULT_MAX_BYTES:
                report["notes"].append("output.json is over 256 KB, so the run has no Result")
            else:
                try:
                    report["result"] = json.loads(result.read_text(encoding="utf-8"))
                except ValueError:
                    report["notes"].append("output.json is not valid JSON, so the run has no Result")
        elif report["status"] == "succeeded":
            report["notes"].append("no output/output.json, so the run has no Result")

    (out / "run.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("widget", type=Path)
    parser.add_argument("cases", type=Path, nargs="+")
    parser.add_argument("--python")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    widget = args.widget.resolve()
    worst = 0
    for case in args.cases:
        case = case.resolve()
        if not (case / "case.json").is_file():
            print(f"{case.name}: no case.json in {case}")
            worst = max(worst, 2)
            continue
        port = case.parent.parent
        out_root = (args.out or port / "runs" / "local").resolve()
        python, python_note = interpreter(args.python, port)
        report = run_case(widget, case, out_root, python, args.timeout)
        if python_note:
            report["notes"].insert(0, python_note)
        if report["status"] == "succeeded":
            result = "a Result" if report["result"] is not None else "no Result"
            line = f"{case.name}: succeeded in {report['seconds']} s, {len(report['output_files'])} file(s), {result}"
        elif report["status"] == "not run":
            line = f"{case.name}: not run: {report['error']['message']}"
        elif report["status"] == "refused":
            line = f"{case.name}: refused before running: {report['error']['message']}"
            worst = max(worst, 1)
        else:
            line = f"{case.name}: {report['status']} ({report['error']['code']}): {report['error']['message']}"
            worst = max(worst, 1)
        print(line)
        for note in report["notes"]:
            print(f"  note: {note}")
        print(f"  -> {out_root / case.name}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
