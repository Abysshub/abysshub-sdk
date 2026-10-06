from __future__ import annotations

import platform
from importlib import metadata

import pytest
from fake_server import Replay, load_exchanges

from abysshub import Abyss, AbyssError, AsyncAbyss


@pytest.fixture(autouse=True)
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ABYSS_API_KEY", raising=False)
    monkeypatch.delenv("ABYSS_BASE_URL", raising=False)


def test_a_key_goes_to_the_apis_address() -> None:
    assert Abyss(api_key="abyss_sk_x").base_url == "https://api.abysshub.com"


def test_an_abyss_sk_dev_key_goes_to_devs_address() -> None:
    assert Abyss(api_key="abyss_sk_dev_x").base_url == "https://api.dev.abysshub.com"


def test_abyss_base_url_overrides_the_keys_address_and_base_url_overrides_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABYSS_BASE_URL", "http://localhost:8000/")
    assert Abyss(api_key="abyss_sk_dev_x").base_url == "http://localhost:8000"
    assert Abyss(api_key="abyss_sk_dev_x", base_url="http://other").base_url == "http://other"


def test_the_key_comes_from_abyss_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABYSS_API_KEY", "abyss_sk_dev_x")
    assert Abyss().base_url == "https://api.dev.abysshub.com"


def test_no_key_raises_abyss_error() -> None:
    with pytest.raises(AbyssError) as raised:
        Abyss()
    assert raised.value.code == "invalid_api_key"


def test_async_abyss_takes_the_same_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABYSS_API_KEY", "abyss_sk_dev_x")
    abyss = AsyncAbyss(max_retries=0, timeout=5)
    assert (abyss.base_url, abyss.max_retries, abyss.timeout) == ("https://api.dev.abysshub.com", 0, 5)
    monkeypatch.delenv("ABYSS_API_KEY")
    with pytest.raises(AbyssError) as raised:
        AsyncAbyss()
    assert raised.value.code == "invalid_api_key"


def test_max_retries_defaults_to_2() -> None:
    assert Abyss(api_key="abyss_sk_x").max_retries == 2
    assert Abyss(api_key="abyss_sk_x", max_retries=0).max_retries == 0


def test_every_request_sends_the_user_agent() -> None:
    recording = load_exchanges("key.json")[0]
    recording["exchanges"][0]["request"]["headers"]["User-Agent"] = (
        f"abysshub-python/{metadata.version('abysshub')} (python {platform.python_version()})"
    )
    server = Replay(recording, "abyss_sk_x")
    try:
        with Abyss(api_key="abyss_sk_x", base_url=server.base) as abyss:
            abyss.key()
        assert server.problems == []
    finally:
        server.close()
