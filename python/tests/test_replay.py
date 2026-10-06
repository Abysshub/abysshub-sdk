"""Every recorded exchange the Python library covers, replayed through the fake server,
by ``Abyss`` and by ``AsyncAbyss``. Each must reach the same outcome as in JS."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from caller import caller_input, perform, perform_async, with_files
from fake_server import Replay, load_exchanges

from abysshub import Abyss, AbyssError, AsyncAbyss, AsyncRun, Run

KEY = "abyss_sk_fake_for_tests"
RECORDINGS = load_exchanges()


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


def call_sync(base: str, call: dict[str, Any], dir: Path, files: dict[str, str]) -> tuple[Any, Any, Any]:
    """The recorded call through ``Abyss``: its value, its error and what ``run.save()`` answered."""
    save = call.get("save")
    with Abyss(api_key=KEY, base_url=base, **(call.get("client") or {})) as abyss:
        try:
            value, error = perform(abyss, call, caller_input(call.get("input") or {}, dir, files)), None
        except AbyssError as raised:
            value, error = None, raised
        saved = value.save(dir / save) if save and isinstance(value, Run) else None
    return value, error, saved


async def call_async(base: str, call: dict[str, Any], dir: Path, files: dict[str, str]) -> tuple[Any, Any, Any]:
    """The recorded call through ``AsyncAbyss``."""
    save = call.get("save")
    async with AsyncAbyss(api_key=KEY, base_url=base, **(call.get("client") or {})) as abyss:
        try:
            value, error = await perform_async(abyss, call, caller_input(call.get("input") or {}, dir, files)), None
        except AbyssError as raised:
            value, error = None, raised
        saved = await value.save(dir / save) if save and isinstance(value, AsyncRun) else None
    return value, error, saved


@pytest.mark.parametrize("client", ["Abyss", "AsyncAbyss"])
@pytest.mark.parametrize("recording", RECORDINGS, ids=[r["name"] for r in RECORDINGS])
def test_replay(recording: dict[str, Any], client: str) -> None:
    call = recording["call"]
    files = call.get("files") or {}
    save = call.get("save")
    server = Replay(recording, KEY)
    try:
        with with_files(files) as dir:
            if client == "Abyss":
                value, error, saved = call_sync(server.base, call, dir, files)
            else:
                value, error, saved = asyncio.run(call_async(server.base, call, dir, files))

            assert server.problems == []
            assert server.remaining() == 0, "every recorded request was sent"
            outcome = recording["outcome"]
            if "run" in outcome:
                assert isinstance(value, (Run, AsyncRun)), f"expected a run, got {error!r}"
                assert_fields(value, outcome["run"], "run")
            elif "value" in outcome:
                assert value is not None, f"expected a value, got {error!r}"
                assert_fields(value, outcome["value"], "value")
            else:
                assert error is not None, f"expected an AbyssError, got {value!r}"
                fields = dict(outcome["error"])
                run = fields.pop("run")
                assert_fields(error, fields, "error")
                if run is None:
                    assert error.run is None
                else:
                    assert_fields(error.run, run, "error.run")
            if "saved" in outcome:
                assert saved == [dir / save / path for path in outcome["saved"]], "run.save() returns the paths it wrote"
                for path, content in outcome["saved"].items():
                    assert (dir / save / path).read_text("utf-8") == content, f"saved {path}"
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


def test_async_returns_async_runs_and_raises_them() -> None:
    recordings = {r["name"]: r for r in RECORDINGS}

    async def work(name: str) -> Any:
        server = Replay(recordings[name], KEY)
        try:
            async with AsyncAbyss(api_key=KEY, base_url=server.base) as abyss:
                try:
                    return await abyss.run("widget_131", {"amount": 250000})
                except AbyssError as error:
                    return error
        finally:
            server.close()

    assert isinstance(asyncio.run(work("run-held-success.json")), AsyncRun)
    failed = asyncio.run(work("run-held-failure.json"))
    assert isinstance(failed, AbyssError) and isinstance(failed.run, AsyncRun)
