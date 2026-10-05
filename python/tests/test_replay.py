"""Every recorded exchange the Python library covers, replayed through the fake server.
Each must reach the same outcome as in JS."""
from __future__ import annotations

from typing import Any

import pytest
from fake_server import Replay, load_exchanges

from abysshub import Abyss, AbyssError, Run

KEY = "abyss_sk_fake_for_tests"
RECORDINGS = load_exchanges("run-*.json")


def assert_fields(actual: Any, expected: Any, where: str) -> None:
    """The fields ``expected`` names, however deep: a list must have its length, and an
    object at least the fields it names."""
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{where} is a list"
        assert len(actual) == len(expected), f"{where} length"
        for index, item in enumerate(expected):
            assert_fields(actual[index], item, f"{where}[{index}]")
    elif isinstance(expected, dict):
        assert actual is not None, f"{where} is an object"
        for name, value in expected.items():
            field = actual[name] if isinstance(actual, dict) else getattr(actual, name)
            assert_fields(field, value, f"{where}.{name}")
    else:
        assert actual == expected, where


def perform(abyss: Abyss, call: dict[str, Any]) -> Any:
    """The recorded call, made through the method it names."""
    method = call.get("method", "run")
    options = call.get("options") or {}
    if method == "run":
        return abyss.run(call["widget"], call.get("input") or {}, **options)
    raise AssertionError(f"no such method: {method}")


@pytest.mark.parametrize("recording", RECORDINGS, ids=[r["name"] for r in RECORDINGS])
def test_replay(recording: dict[str, Any]) -> None:
    server = Replay(recording, KEY)
    try:
        client = recording["call"].get("client") or {}
        with Abyss(api_key=KEY, base_url=server.base, **client) as abyss:
            try:
                value, error = perform(abyss, recording["call"]), None
            except AbyssError as raised:
                value, error = None, raised

        assert server.problems == []
        assert server.remaining() == 0, "every recorded request was sent"
        outcome = recording["outcome"]
        if "run" in outcome:
            assert isinstance(value, Run), f"expected a run, got {error!r}"
            assert_fields(value, outcome["run"], "run")
        else:
            assert error is not None, f"expected an AbyssError, got {value!r}"
            fields = dict(outcome["error"])
            run = fields.pop("run")
            assert_fields(error, fields, "error")
            if run is None:
                assert error.run is None
            else:
                assert_fields(error.run, run, "error.run")
    finally:
        server.close()


def test_result_is_a_dict() -> None:
    recording = next(r for r in RECORDINGS if r["name"] == "run-held-success.json")
    server = Replay(recording, KEY)
    try:
        with Abyss(api_key=KEY, base_url=server.base) as abyss:
            run = abyss.run("widget_131", {"amount": 250000})
        assert run.result == {"approved": True, "rate": 0.042}
        assert isinstance(run.result, dict)
    finally:
        server.close()
