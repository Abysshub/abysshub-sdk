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
from abysshub._env import parse_env

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
            before = {path: (dir / path).read_bytes() for path in call["files"]}
            commands = [call["command"], *(call.get("then") or [])]
            # Each command before the last must go through.
            for command in commands[:-1]:
                assert main([*command, str(dir)]) == 0, capsys.readouterr().err
            exit = main([*commands[-1], str(dir)])
            printed = capsys.readouterr()

            assert server.problems == []
            assert server.remaining() == 0, "every recorded request was sent"
            assert exit == outcome["exit"], printed.err
            for text in outcome["printed"]:
                assert text in printed.out + printed.err, f"printed {text}"
            for path, fields in outcome["written"].items():
                if isinstance(fields, str):
                    assert (dir / path).read_text("utf-8") == fields, path
                else:
                    assert_fields(json.loads((dir / path).read_text("utf-8")), fields, path)
            for path, content in before.items():
                if path not in outcome["written"]:
                    assert (dir / path).read_bytes() == content, f"{path} was left as it was"
            # A root .env's names are printed, never its values, an Abyss key left out included.
            for value in parse_env(call["files"].get(".env", "")).values():
                assert not value or value not in printed.out + printed.err, "printed a value of the .env"
    finally:
        server.close()


def test_publish_without_a_key_prints_every_fault_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = Replay({"exchanges": []}, KEY)
    try:
        with with_files({"run.py": "print('words')\n", "requirements.txt": "\n"}) as dir:
            monkeypatch.delenv("ABYSS_API_KEY", raising=False)
            monkeypatch.setenv("ABYSS_BASE_URL", server.base)
            exit = main(["publish", str(dir)])
            printed = capsys.readouterr()

            assert server.problems == []
            assert exit == 1
            assert "publish_file_missing" in printed.err
            assert "invalid_api_key" in printed.err
    finally:
        server.close()


def test_a_root_env_gives_the_values_python_dotenv_gives() -> None:
    text = (
        'A="quoted" # note\n'
        "B='single' # note\n"
        'C="line\\nbreak"\n'
        "C2='line\\nkept'\n"
        "D=plain # note\n"
        "E=a#b\n"
        "export F = spaced\n"
        "# a comment\n"
        "G=\n"
        "H\n"
        "K='abyss_sk_live_4f1c' # mine\n"
    )
    assert parse_env(text) == {
        "A": "quoted",
        "B": "single",
        "C": "line\nbreak",
        "C2": "line\\nkept",
        "D": "plain",
        "E": "a#b",
        "F": "spaced",
        "G": "",
        "K": "abyss_sk_live_4f1c",
    }
