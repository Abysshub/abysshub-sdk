from importlib.metadata import metadata, requires

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
