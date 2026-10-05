"""The nightly live run of the Python library (.github/workflows/live.yml). The workflow
installs the library the way a caller installs it, then runs this file: a few calls against
dev's /v1, then the probe Widget's code exactly as its page shows it. Each check prints one
line; a broken one prints its code and request_id, and the run exits 1."""

from __future__ import annotations

import hashlib
import os
import re
import runpy
import sys
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import httpx

from abysshub import Abyss, AbyssError, Run, file

NOT_A_FIELD = "abysshub_live_not_a_field"
"""A key the probe has no Field for, so a press with it is refused as `invalid_input`."""
TIMEOUT = 600
"""The seconds each call waits at most, so a stuck run turns the night red instead of hanging it."""


def main() -> int:
    config("ABYSS_API_KEY")
    base = config("ABYSS_BASE_URL").rstrip("/")
    widget = config("ABYSS_PROBE_WIDGET")
    match = re.fullmatch(r"widget_([1-9][0-9]*)", widget)
    if match is None:
        return fail(f"ABYSS_PROBE_WIDGET is {widget!r}, not a listed Widget's widget_<id>.")

    text = f"abysshub live run (python), {datetime.now(timezone.utc).isoformat()}"
    sent = f"A probe file from {text}.\n"
    abyss = Abyss(timeout=TIMEOUT)
    runs: list[Run] = []
    failures = 0

    def check(name: str, call: Callable[[], str]) -> None:
        nonlocal failures
        try:
            print(f"ok   {name}: {call()}", flush=True)
        except Exception as error:
            failures += 1
            print(f"::error::{name}: {describe(error)}", flush=True)

    def ran(run: Run) -> str:
        runs.append(run)
        return f"{run.id} {run.status}, price {run.price}, {len(run.output_files)} output file(s)"

    with tempfile.TemporaryDirectory(prefix="abysshub-live-") as tmp:
        dir = Path(tmp)

        check("run() with a JSON input", lambda: ran(abyss.run(widget, {"text": text})))

        def file_input() -> str:
            path = dir / "probe.txt"
            path.write_text(sent, encoding="utf-8")
            run = abyss.run(widget, {"text": text, "file": file(str(path))})
            echoed = ((run.result or {}).get("file") or {}).get("sha256")
            if echoed != sha256(sent):
                raise Broke(f"{run.id}: the probe got a file with sha256 {echoed}, not the one sent")
            return ran(run)

        check("run() with a file input", file_input)

        def save() -> str:
            if not runs:
                raise Broke("no run to save: both presses broke")
            saved = 0
            for run in runs:
                into = dir / "saved" / run.id
                saved += len(run.save(into))
                for output in run.output_files:
                    size = (into / output.path).stat().st_size
                    if size != output.size:
                        raise Broke(f"{run.id}: {output.path} saved {size} bytes, its run says {output.size}")
                echo = (into / "echo.txt").read_text(encoding="utf-8")
                if echo != f"{text}\n":
                    raise Broke(f"{run.id}: echo.txt holds {echo!r}, not the text sent")
            return f"{saved} file(s) saved from {len(runs)} run(s), each at its size"

        check("run.save()", save)

        def refusal() -> str:
            try:
                abyss.run(widget, {"text": text, NOT_A_FIELD: True})
            except AbyssError as error:
                if error.code != "invalid_input":
                    raise
                if not error.request_id:
                    raise Broke("the refusal carries no request_id") from error
                return f"status {error.status}, param {error.param}, request_id {error.request_id}"
            raise Broke(f"a press with the key {NOT_A_FIELD} was not refused")

        check("a refusal (invalid_input)", refusal)

        def panel() -> str:
            page = f"{base}/api/products/{match[1]}/api-access"
            response = httpx.get(page, headers={"Accept": "application/json"}, timeout=30)
            if response.is_error:
                waf = " (with no JSON body, that is dev's WAF)" if response.status_code == 403 else ""
                raise Broke(f"GET {page} answered {response.status_code}{waf}")
            code: str = response.json()["data"]["python"]
            at = Path(tempfile.mkdtemp(prefix="panel-", dir=dir))
            for name in re.findall(r'\bfile\("([^"]+)"\)', code):
                (at / name).write_text(sent, encoding="utf-8")
            (at / "panel.py").write_text(code, encoding="utf-8")
            here = os.getcwd()
            os.chdir(at)
            try:
                runpy.run_path(str(at / "panel.py"), run_name="__main__")
            finally:
                os.chdir(here)
            lines = len(code.split("\n"))
            if "run.save(" not in code:
                return f"{lines} lines ran"
            saved = [path for path in (at / "output").rglob("*") if path.is_file()] if (at / "output").is_dir() else []
            if not saved:
                raise Broke("the code saves the outputs, and none were saved")
            return f"{lines} lines ran and saved {len(saved)} file(s)"

        check("the Widget's code from its page", panel)

    abyss.close()
    if failures:
        return fail(f"{failures} of 5 checks broke.")
    return 0


class Broke(Exception):
    """A check's own finding: its message says it all, so it prints without a traceback."""


def describe(error: Exception) -> str:
    if isinstance(error, Broke):
        return str(error)
    if not isinstance(error, AbyssError):
        return "".join(traceback.format_exception(type(error), error, error.__traceback__)).rstrip()
    run = f", run {error.run.id}" if error.run else ""
    return f"{error.code} (status {error.status}, request_id {error.request_id}{run}): {error.message}"


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def config(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(fail(f"{name} is not set (see .github/workflows/live.yml)."))
    return value


def fail(message: str) -> int:
    print(f"::error::{message}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
