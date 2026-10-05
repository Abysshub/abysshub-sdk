from __future__ import annotations

from dataclasses import dataclass

import httpx

CONNECT_TIMEOUT = 10.0
"""Seconds to connect."""

SILENCE_TIMEOUT = 30.0
"""Seconds a response may stay silent before it counts as a cut."""


def timeouts(connect: float = CONNECT_TIMEOUT, silence: float = SILENCE_TIMEOUT) -> httpx.Timeout:
    """httpx's timeouts: ``connect`` to connect, and ``silence`` between any two reads."""
    return httpx.Timeout(silence, connect=connect)


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
) -> Answer:
    """Sends one request and reads its whole body.

    A failure before the headers raises ``httpx.TransportError``; a cut after them
    answers ``text=None``, so the caller can re-attach.
    """
    with client.stream(method, url, headers=headers, content=content) as response:
        try:
            body = b"".join(response.iter_bytes())
        except httpx.TransportError:
            return Answer(response.status_code, response.headers, None)
    return Answer(response.status_code, response.headers, body.decode("utf-8", errors="replace"))
