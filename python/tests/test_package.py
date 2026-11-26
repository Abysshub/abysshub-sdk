import ast
import re
import subprocess
import sys
from importlib.metadata import metadata, requires
from pathlib import Path

from packaging.requirements import Requirement

PROJECT = Path(__file__).resolve().parent.parent


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


def check(tool, *args):
    return subprocess.run([sys.executable, "-m", tool, *args], cwd=PROJECT, capture_output=True, text=True)


def test_vulture_finds_no_dead_code_beyond_its_whitelist_and_the_whitelist_only_shrinks():
    done = check("vulture")
    assert done.returncode == 0, done.stdout
    whitelist = ast.parse((PROJECT / "vulture_whitelist.py").read_text())
    recorded = {node.value.id for node in whitelist.body}
    found = set(re.findall(r"'([^']+)'", check("vulture", "src", "tests").stdout))
    assert recorded <= found, f"no longer found, so remove from vulture_whitelist.py: {recorded - found}"


def test_deptry_finds_every_import_declared_and_every_dependency_imported():
    done = check("deptry", "src")
    assert done.returncode == 0, done.stdout + done.stderr


def test_ruff_finds_no_commented_out_code():
    done = check("ruff", "check", "src", "tests")
    assert done.returncode == 0, done.stdout
