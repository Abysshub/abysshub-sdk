#!/usr/bin/env python3
"""Run a Port's Cases on Abyss, through /v1, with the abysshub library.

    python3 check_abyss.py <widget> <case-folder> [<case-folder> ...]

<widget> is the Widget's page address (https://abysshub.com/widgets/123/...),
its id (widget_123) or its private token. Only Cases whose case.json says
"abyss": true are sent; the rest stay local. The key is ABYSS_API_KEY, read
from the environment or from <port>/.env, where <port> is the folder holding
cases/. Each run's run.json and output/ are written to <port>/runs/abyss/<case>/.
It first prints the Widget's private link, and at the end the ids of the runs
it made.

Needs `pip install abysshub`; Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from abysshub import Abyss, AbyssError, file
except ImportError:
    sys.exit("This needs the abysshub library: pip install abysshub")

DEFAULT_BASE = "https://api.abysshub.com"
DEV_KEY_PREFIX = "abyss_sk_dev_"
DEV_BASE = "https://api.dev.abysshub.com"


def widget_id(given: str) -> str:
    """widget_<n> or a private token, from a page address, an id or a token."""
    given = given.strip()
    match = re.search(r"/widgets/([^/?#]+)", given)
    segment = match.group(1) if match else given
    if re.fullmatch(r"\d+", segment):
        return f"widget_{segment}"
    return segment


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(name, value)


def base_url() -> str:
    if os.environ.get("ABYSS_BASE_URL"):
        return os.environ["ABYSS_BASE_URL"].rstrip("/")
    if os.environ.get("ABYSS_API_KEY", "").startswith(DEV_KEY_PREFIX):
        return DEV_BASE
    return DEFAULT_BASE


def available(base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/v1/openapi.json", timeout=20) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def with_files(value, case: Path):
    """case.json's {"file": path} becomes file(path), relative to the case folder."""
    if isinstance(value, dict) and set(value) == {"file"}:
        return file(str(case / value["file"]))
    if isinstance(value, list) and value and all(isinstance(v, dict) and set(v) == {"file"} for v in value):
        return [file(str(case / v["file"])) for v in value]
    return value


def record(run, report: dict, out: Path) -> None:
    report.update({
        "id": run.id,
        "status": run.status,
        "price": run.price,
        "result": run.result,
        "error": {"code": run.error.code, "message": run.error.message} if run.error else None,
        "output_files": [{"path": f.path, "size": f.size} for f in run.output_files],
    })
    if run.output_files:
        run.save(out / "output")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("widget")
    parser.add_argument("cases", type=Path, nargs="+")
    args = parser.parse_args()

    cases = [c.resolve() for c in args.cases]
    port = cases[0].parent.parent
    load_dotenv(port / ".env")
    if not os.environ.get("ABYSS_API_KEY"):
        sys.exit(f"No ABYSS_API_KEY: ask the Creator to put it in {port / '.env'}")
    base = base_url()
    if not available(base):
        print(f"The Abyss step isn't available yet: {base} does not answer /v1. The Check ends with the local runs.")
        return 3

    widget = widget_id(args.widget)
    made = []
    worst = 0
    with Abyss(base_url=base) as abyss:
        try:
            print(f"The Widget's link (its private link while it is private): {abyss.widgets.get(widget).url}")
        except AbyssError as error:
            print(f"{widget}: {error.code}: {error.message} (is the address right, and the key the Creator's own?)")
            return 2
        for case in cases:
            spec = json.loads((case / "case.json").read_text(encoding="utf-8"))
            if spec.get("abyss") is not True:
                print(f"{case.name}: kept local")
                continue
            out = port / "runs" / "abyss" / case.name
            out.mkdir(parents=True, exist_ok=True)
            report: dict = {"case": case.name, "where": "abyss", "widget": widget}
            started = time.monotonic()
            try:
                inputs = {name: with_files(value, case) for name, value in spec.get("input", {}).items()}
                record(abyss.run(widget, inputs), report, out)
            except AbyssError as error:
                if error.run is not None:
                    record(error.run, report, out)
                else:
                    report.update({"status": "refused", "error": {"code": error.code, "message": error.message},
                                   "param": error.param, "request_id": error.request_id, "id": error.run_id})
            report["seconds"] = round(time.monotonic() - started, 1)
            (out / "run.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            if report.get("id"):
                made.append(report["id"])
            if report["status"] == "succeeded":
                print(f"{case.name}: succeeded in {report['seconds']} s, {len(report['output_files'])} file(s), "
                      f"{'a Result' if report['result'] is not None else 'no Result'} ({report['id']})")
            else:
                worst = 1
                print(f"{case.name}: {report['status']} ({report['error']['code']}): {report['error']['message']}"
                      f" ({report.get('id') or report.get('request_id')})")
            print(f"  -> {out}")
    print("Runs made on Abyss: " + (", ".join(made) if made else "none"))
    return worst


if __name__ == "__main__":
    sys.exit(main())
