from __future__ import annotations

from collections.abc import Callable

import pytest
from fake_server import Replay, load_exchanges

from abysshub import Abyss, AbyssError

KEY = "abyss_sk_fake_for_tests"
RECORDING = load_exchanges("timeout-reattach.json")[0]
WIDGET = RECORDING["call"]["widget"]
INPUT = RECORDING["call"]["input"]
ID = RECORDING["outcome"]["error"]["run"]["id"]


def against(work: Callable[[str], None]) -> None:
    server = Replay(RECORDING, KEY)
    try:
        work(server.base)
        assert server.problems == []
        assert server.remaining() == 0, "every recorded request was sent"
    finally:
        server.close()


def test_the_clients_timeout_applies_to_every_call() -> None:
    def work(base: str) -> None:
        with Abyss(api_key=KEY, base_url=base, timeout=0.3) as abyss:
            assert abyss.timeout == 0.3
            with pytest.raises(AbyssError) as raised:
                abyss.run(WIDGET, INPUT)
        assert raised.value.code == "timeout"
        assert raised.value.run is not None and raised.value.run.id == ID

    against(work)


def test_a_calls_timeout_overrides_the_clients() -> None:
    def work(base: str) -> None:
        with Abyss(api_key=KEY, base_url=base, timeout=3600) as abyss:
            with pytest.raises(AbyssError) as raised:
                abyss.run(WIDGET, INPUT, timeout=0.3)
        assert raised.value.code == "timeout"
        assert raised.value.run is not None and raised.value.run.status == "queued"

    against(work)


def test_there_is_no_timeout_by_default() -> None:
    assert Abyss(api_key=KEY).timeout is None
