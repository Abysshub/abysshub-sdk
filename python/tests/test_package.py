import subprocess
import sys
from importlib.metadata import metadata, requires
from pathlib import Path

from packaging.requirements import Requirement


def test_httpx_is_the_only_runtime_dependency():
    reqs = [Requirement(r) for r in requires("abysshub") or []]
    runtime = {r.name for r in reqs if r.marker is None or "extra" not in str(r.marker)}
    assert runtime <= {"httpx"}


def test_pypi_page_says_the_job_carries_keywords_and_links_to_the_docs():
    meta = metadata("abysshub")
    assert "Abyss Widget" in meta["Summary"]
    assert {"abyss", "abysshub", "widget"} <= set(meta["Keywords"].split(","))
    assert "Homepage, https://abysshub.com/docs#api" in meta.get_all("Project-URL")


def test_the_command_runs_as_abysshub_and_as_python_m_abysshub():
    script = Path(sys.executable).parent / "abysshub"
    for command in ([str(script)], [sys.executable, "-m", "abysshub"]):
        done = subprocess.run([*command, "publish", "--help"], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        assert "folder" in done.stdout
