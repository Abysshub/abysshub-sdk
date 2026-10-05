from importlib.metadata import requires

from packaging.requirements import Requirement


def test_httpx_is_the_only_runtime_dependency():
    reqs = [Requirement(r) for r in requires("abysshub") or []]
    runtime = {r.name for r in reqs if r.marker is None or "extra" not in str(r.marker)}
    assert runtime <= {"httpx"}
