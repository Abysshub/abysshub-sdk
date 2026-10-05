from __future__ import annotations

from typing import Any

import httpx
import pytest
from fake_server import Replay

from abysshub._http import request, timeouts


def answering(response: dict[str, Any]) -> Replay:
    return Replay({"exchanges": [{"request": {"method": "GET", "path": "/"}, "response": response}]}, "abyss_sk_x")


def get(server: Replay, silence: float = 1.0) -> Any:
    with httpx.Client(timeout=timeouts(connect=1.0, silence=silence)) as client:
        return request(client, "GET", f"{server.base}/", {})


def test_the_timeouts_are_10_s_to_connect_and_30_s_of_silence() -> None:
    assert timeouts() == httpx.Timeout(30.0, connect=10.0)


def test_silence_after_the_headers_counts_as_a_cut() -> None:
    server = answering({"status": 200, "chunks": [" "], "hold": True})
    try:
        answer = get(server, silence=0.1)
        assert answer.status == 200
        assert answer.text is None
    finally:
        server.close()


def test_a_cut_after_the_headers_answers_no_text() -> None:
    server = answering({"status": 200, "headers": {"Location": "{base}/v1/runs/run_x"}, "chunks": [" ", " "], "cut": True})
    try:
        answer = get(server)
        assert answer.text is None
        assert answer.headers["location"] == f"{server.base}/v1/runs/run_x"
    finally:
        server.close()


def test_a_drop_before_any_headers_raises() -> None:
    server = answering({"drop": True})
    try:
        with pytest.raises(httpx.TransportError):
            get(server)
    finally:
        server.close()


def test_a_whole_body_keeps_its_leading_spaces_for_the_caller_to_skip() -> None:
    server = answering({"status": 200, "chunks": ["  "], "body": {"ok": True}})
    try:
        assert get(server).text == '  {"ok": true}'
    finally:
        server.close()
