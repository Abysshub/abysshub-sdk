from __future__ import annotations

import asyncio

import pytest

from abysshub import _async_client, _client


@pytest.fixture(autouse=True)
def no_real_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes every pause the library waits between two tries near zero, so no test sleeps through a real one."""

    async def wait(seconds: float) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(_client, "_wait", lambda seconds: None)
    monkeypatch.setattr(_async_client, "_wait", wait)
