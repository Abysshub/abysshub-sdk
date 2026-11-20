"""Every recorded command, run as ``abysshub`` with its folder against the fake server.
A command is the Python package's alone, so only pytest replays these recordings."""
from __future__ import annotations

import json
from typing import Any

import pytest
from caller import with_files
from fake_server import Replay, load_exchanges
from test_replay import KEY, assert_fields

from abysshub._command import main

COMMANDS = [recording for recording in load_exchanges() if "command" in recording["call"]]


@pytest.mark.parametrize("recording", COMMANDS, ids=[r["name"] for r in COMMANDS])
def test_command(recording: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    call = recording["call"]
    outcome = recording["outcome"]
    server = Replay(recording, KEY)
    try:
        with with_files(call["files"]) as dir:
            monkeypatch.setenv("ABYSS_API_KEY", KEY)
            monkeypatch.setenv("ABYSS_BASE_URL", server.base)
            exit = main([*call["command"], str(dir)])
            printed = capsys.readouterr()

            assert server.problems == []
            assert server.remaining() == 0, "every recorded request was sent"
            assert exit == outcome["exit"], printed.err
            for text in outcome["printed"]:
                assert text in printed.out + printed.err, f"printed {text}"
            for path, fields in outcome["written"].items():
                assert_fields(json.loads((dir / path).read_text("utf-8")), fields, path)
    finally:
        server.close()
