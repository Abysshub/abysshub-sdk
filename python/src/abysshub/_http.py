from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

CONNECT_TIMEOUT = 10.0
"""Seconds to connect."""

SILENCE_TIMEOUT = 30.0
"""Seconds a response may stay silent before it counts as a cut."""


def timeouts(connect: float = CONNECT_TIMEOUT, silence: float = SILENCE_TIMEOUT) -> httpx.Timeout:
    """httpx's timeouts: ``connect`` to connect, and ``silence`` between any two reads."""
    return httpx.Timeout(silence, connect=connect)


class Stopped(Exception):
    """The call's deadline passed while its request was waiting."""


@dataclass
class Answer:
    status: int
    headers: httpx.Headers
    text: str | None
    """The whole body, or None when the connection was cut or went silent after the headers."""


def request(
    client: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str],
    content: bytes | None = None,
    timeout: httpx.Timeout | None = None,
    deadline: float | None = None,
) -> Answer:
    """Sends one request and reads its whole body.

    A failure before the headers raises ``httpx.TransportError``; a cut after them
    answers ``text=None``, so the caller can re-attach. Past ``deadline`` (a
    ``time.monotonic()`` reading), a hold that still sends its spaces raises ``Stopped``.
    """
    with client.stream(
        method, url, headers=headers, content=content, timeout=timeout or client.timeout
    ) as response:
        chunks = []
        try:
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                if deadline is not None and time.monotonic() >= deadline:
                    raise Stopped
        except httpx.TransportError:
            return Answer(response.status_code, response.headers, None)
    return Answer(response.status_code, response.headers, b"".join(chunks).decode("utf-8", errors="replace"))


async def arequest(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    content: bytes | None = None,
    timeout: httpx.Timeout | None = None,
    deadline: float | None = None,
) -> Answer:
    """``request()`` on httpx's async client."""
    async with client.stream(
        method, url, headers=headers, content=content, timeout=timeout or client.timeout
    ) as response:
        chunks = []
        try:
            async for chunk in response.aiter_bytes():
                chunks.append(chunk)
                if deadline is not None and time.monotonic() >= deadline:
                    raise Stopped
        except httpx.TransportError:
            return Answer(response.status_code, response.headers, None)
    return Answer(response.status_code, response.headers, b"".join(chunks).decode("utf-8", errors="replace"))
